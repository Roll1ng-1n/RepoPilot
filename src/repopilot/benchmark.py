"""A small, reproducible benchmark runner for the two RepoPilot engines.

The benchmark module deliberately owns composition, while the engines keep their
normal seams.  A caller can provide an executor for each engine in tests; the
default executors are the only code that starts a model or Docker container.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, field, replace
from enum import Enum
from pathlib import Path
from typing import Any, Protocol

from minisweagent.agents import get_agent
from minisweagent.config import builtin_config_dir, get_config_from_spec
from minisweagent.environments import get_environment
from minisweagent.models import get_model
from minisweagent.utils.serialize import recursive_merge
from repopilot.approval import ApprovalContext
from repopilot.artifacts import RunArtifacts
from repopilot.budget import RunBudget
from repopilot.context import ContextManager
from repopilot.environment import DockerExecutionEnvironment, DockerProxyMode, docker_proxy_run_args
from repopilot.evaluation import (
    CATEGORIES,
    REQUIREMENTS,
    ScenarioObserver,
    aggregate,
    evaluate,
    markdown,
    normalize_trace,
    scenario_audit,
)
from repopilot.model import AssistantTurn, LiteLLMToolCallingModel
from repopilot.plan import PlanHistory
from repopilot.pricing import (
    OPENAI_STANDARD_PRICING_AS_OF,
    OPENAI_STANDARD_PRICING_SOURCE,
    estimate_openai_standard_cost,
)
from repopilot.runtime import AgentRunResult, AgentRuntime
from repopilot.tools import create_tool_registry

DEFAULT_BENCHMARK_IMAGE = "repopilot-benchmark:py312-git"


class EngineVariant(str):
    """Stable adapter/ablation identity, independent of the two built-in engines."""

    @property
    def value(self) -> str:
        return str(self)


class BenchmarkEngine(str, Enum):
    """Engines which can solve one benchmark task."""

    BASELINE = "baseline"
    REPOPILOT = "repopilot"


Engine = BenchmarkEngine


BUDGET_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "max_steps": ("max_steps", "steps"),
    "max_replans": ("max_replans", "replans"),
    "max_consecutive_failures": ("max_consecutive_failures", "consecutive_failures"),
    "command_timeout_seconds": ("command_timeout_seconds", "command_timeout", "command_timeout_s"),
    "max_run_seconds": ("max_run_seconds", "run_timeout_seconds", "timeout_seconds"),
}


def declared_budget_fields(value: Mapping[str, Any]) -> frozenset[str]:
    """Return the canonical budget fields an explicit mapping declares."""

    return frozenset(destination for destination, candidates in BUDGET_FIELD_ALIASES.items() if any(c in value for c in candidates))


@dataclass(frozen=True)
class BenchmarkBudget:
    """The common resource settings passed to both engines where supported."""

    max_steps: int = 30
    max_replans: int = 2
    max_consecutive_failures: int = 3
    command_timeout_seconds: float = 300.0
    max_run_seconds: float = 30.0 * 60.0

    def to_run_budget(self, *, max_run_seconds: float | None = None) -> RunBudget:
        return RunBudget(
            max_steps=self.max_steps,
            max_replans=self.max_replans,
            max_consecutive_failures=self.max_consecutive_failures,
            command_timeout_seconds=self.command_timeout_seconds,
            max_run_seconds=self.max_run_seconds if max_run_seconds is None else max_run_seconds,
        )

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> BenchmarkBudget:
        values: dict[str, Any] = {}
        for destination, candidates in BUDGET_FIELD_ALIASES.items():
            for candidate in candidates:
                if candidate in value:
                    values[destination] = value[candidate]
                    break
        return cls(**values)


@dataclass(frozen=True)
class BenchmarkModel:
    """Model settings shared by baseline and RepoPilot."""

    model_name: str
    model_kwargs: dict[str, Any] = field(default_factory=dict)
    base_url: str | None = None
    api_key: str | None = field(default=None, repr=False)

    def public_dict(self) -> dict[str, Any]:
        # Provider credentials and endpoint URLs are runtime-only.  The model
        # shape remains useful in public reports without retaining either.
        model_kwargs = {
            key: value
            for key, value in self.model_kwargs.items()
            if key not in {"api_key", "api_base", "base_url", "base_url_override"}
        }
        return {"model_name": self.model_name, "model_kwargs": model_kwargs}


@dataclass(frozen=True)
class BenchmarkTask:
    """One fixed snapshot, task prompt, and host-only verifier."""

    task_id: str
    task: str
    snapshot: Path
    snapshot_sha256: str
    verifier_command: str | None = None
    success_condition: str | dict[str, Any] = "The hidden verifier exits with code 0."
    timeout_seconds: float = 300.0
    manifest_path: Path | None = None
    snapshot_revision: str | None = None
    verifier_path: Path | None = None
    verifier_timeout_seconds: float | None = None
    run_budget: BenchmarkBudget | None = None
    run_budget_declared: frozenset[str] = frozenset()
    category: str = "simple"
    capabilities: tuple[str, ...] = ()
    behavior_requirements: tuple[str, ...] = ()
    behavior_spec: dict[str, Any] = field(default_factory=dict)
    behavior_verifier_path: Path | None = None
    approval_policy: str = "approve"
    experimental: bool = False

    @property
    def id(self) -> str:
        """Short alias useful to callers and manifest-driven tests."""

        return self.task_id

    @property
    def revision(self) -> str | None:
        """Short alias for the immutable snapshot revision."""

        return self.snapshot_revision

    @classmethod
    def from_manifest(cls, manifest_path: Path) -> BenchmarkTask:
        manifest_path = manifest_path.resolve()
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"Benchmark manifest must contain an object: {manifest_path}")

        task_id = _first_string(payload, "task_id", "id", "name") or manifest_path.parent.name
        task = _first_string(payload, "task_statement", "task", "problem_statement", "description")
        if not task:
            raise ValueError(f"Benchmark manifest has no task description: {manifest_path}")

        snapshot_value = payload.get("snapshot", payload.get("snapshot_path", payload.get("repository")))
        expected_sha = _first_string(payload, "snapshot_sha256", "snapshot_hash", "sha256")
        snapshot_revision: str | None = None
        if isinstance(snapshot_value, dict):
            expected_sha = expected_sha or _first_string(snapshot_value, "sha256", "sha", "snapshot_sha256")
            snapshot_revision = _first_string(snapshot_value, "revision", "ref", "commit")
            snapshot_value = snapshot_value.get("path", snapshot_value.get("directory"))
        if not isinstance(snapshot_value, str) or not snapshot_value:
            raise ValueError(f"Benchmark manifest has no snapshot path: {manifest_path}")
        if not expected_sha:
            raise ValueError(f"Benchmark manifest has no canonical snapshot SHA256: {manifest_path}")
        snapshot = (manifest_path.parent / snapshot_value).resolve()
        if not snapshot.is_dir():
            raise FileNotFoundError(f"Benchmark snapshot does not exist: {snapshot}")

        verifier_value = payload.get(
            "hidden_verifier",
            payload.get("verifier", payload.get("verification", payload.get("verification_command"))),
        )
        verifier_command = verifier_value if isinstance(verifier_value, str) else None
        verifier_data = verifier_value if isinstance(verifier_value, dict) else {}
        verifier_path: Path | None = None
        if isinstance(verifier_value, dict):
            execution = verifier_value.get("execution")
            if execution is not None and execution != "host":
                raise ValueError(f"Benchmark verifier must use host execution: {manifest_path}")
            verifier_path_value = _first_string(verifier_value, "path", "file")
            if verifier_path_value:
                verifier_path = (manifest_path.parent / verifier_path_value).resolve()
                if not verifier_path.is_file():
                    raise FileNotFoundError(f"Benchmark verifier does not exist: {verifier_path}")
                # Keep the normalized path in the legacy field as well so callers
                # that only know about verifier_command still see an absolute path.
                verifier_command = str(verifier_path)
        verifier_command = verifier_command or _first_string(
            verifier_data, "command", "hidden_command", "verification_command"
        )
        if not verifier_command:
            verifier_command = _first_string(payload, "hidden_verifier_command", "verifier_command")
        if not verifier_command:
            raise ValueError(f"Benchmark manifest has no hidden verifier command: {manifest_path}")

        timeout_value = payload.get(
            "timeout_seconds", payload.get("agent_timeout_seconds", payload.get("timeout", 300.0))
        )
        try:
            timeout_seconds = float(timeout_value if timeout_value is not None else 300.0)
        except (TypeError, ValueError) as error:
            raise ValueError(f"Benchmark manifest has invalid timeout: {manifest_path}") from error
        verifier_timeout_value: Any = payload.get("verifier_timeout_seconds", timeout_seconds)
        if isinstance(verifier_data, dict):
            verifier_timeout_value = verifier_data.get(
                "timeout_seconds", verifier_data.get("timeout", verifier_timeout_value)
            )
        try:
            verifier_timeout_seconds = float(
                verifier_timeout_value if verifier_timeout_value is not None else timeout_seconds
            )
        except (TypeError, ValueError) as error:
            raise ValueError(f"Benchmark manifest has invalid verifier timeout: {manifest_path}") from error
        success_condition_value: Any = payload.get(
            "success_condition", payload.get("success", payload.get("expected_result"))
        )
        if success_condition_value is None:
            success_condition_value = verifier_data.get("success_condition", verifier_data.get("condition"))
        if not isinstance(success_condition_value, (str, dict)):
            success_condition_value = cls.success_condition
        run_budget_value = payload.get("run_budget")
        run_budget: BenchmarkBudget | None = None
        if run_budget_value is not None:
            if not isinstance(run_budget_value, Mapping):
                raise ValueError(f"Benchmark manifest has invalid run_budget: {manifest_path}")
            run_budget = BenchmarkBudget.from_dict(run_budget_value)
        behavior_path = payload.get("behavior_verifier")
        behavior_path = (manifest_path.parent / behavior_path).resolve() if isinstance(behavior_path, str) else None
        if behavior_path is not None and not behavior_path.is_file():
            raise FileNotFoundError(f"Behavior verifier does not exist: {behavior_path}")
        approval_policy = payload.get("approval_policy", "approve")
        if approval_policy not in {"approve", "reject"}:
            raise ValueError("approval_policy must be approve or reject")
        category = payload.get("category", "simple")
        requirements = tuple(payload.get("behavior_requirements", ()))
        if category not in CATEGORIES or set(requirements) - REQUIREMENTS:
            raise ValueError(f"Invalid category or behavior requirements: {manifest_path}")
        return cls(
            behavior_verifier_path=behavior_path,
            approval_policy=approval_policy,
            experimental=payload.get("experimental", False),
            category=category,
            capabilities=tuple(payload.get("capabilities", ())),
            behavior_requirements=requirements,
            behavior_spec=payload.get("behavior_spec", {}),
            task_id=task_id,
            task=task,
            snapshot=snapshot,
            snapshot_sha256=expected_sha,
            verifier_command=verifier_command,
            success_condition=success_condition_value,
            timeout_seconds=timeout_seconds,
            manifest_path=manifest_path,
            snapshot_revision=snapshot_revision,
            verifier_path=verifier_path,
            verifier_timeout_seconds=verifier_timeout_seconds,
            run_budget=run_budget,
            run_budget_declared=(
                declared_budget_fields(run_budget_value)
                if isinstance(run_budget_value, Mapping)
                else frozenset()
            ),
        )


@dataclass(frozen=True)
class BenchmarkConfig:
    """Complete fixed configuration for a benchmark run."""

    tasks_directory: Path
    output_directory: Path
    model: BenchmarkModel
    image: str
    budget: BenchmarkBudget = field(default_factory=BenchmarkBudget)
    engines: tuple[BenchmarkEngine, ...] = (BenchmarkEngine.BASELINE, BenchmarkEngine.REPOPILOT)
    task_ids: tuple[str, ...] = ()
    proxy_mode: DockerProxyMode = DockerProxyMode.NONE
    proxy_url: str | None = field(default=None, repr=False)
    # ``image`` is the user-selected tag/reference.  ``image_id`` and
    # ``image_digest`` are populated by Stage 0 after Docker inspection; the
    # former is always usable as an immutable local image reference, while the
    # latter is retained when Docker reports a registry RepoDigest.
    image_id: str | None = None
    image_digest: str | None = None
    repeats: int = 1

    def __post_init__(self) -> None:
        object.__setattr__(self, "engines", tuple(_coerce_engine(e) for e in self.engines))
        if len(set(self.engines)) != len(self.engines) or not self.engines:
            raise ValueError("engines must be unique and nonempty")
        if isinstance(self.repeats, bool) or not isinstance(self.repeats, int) or self.repeats < 1:
            raise ValueError("repeats must be a positive integer")
        if not isinstance(self.proxy_mode, DockerProxyMode):
            object.__setattr__(self, "proxy_mode", DockerProxyMode(str(self.proxy_mode).lower()))
        # Resolve validation without persisting the URL. The actual run args
        # are built by each engine at container start.
        docker_proxy_run_args(self.proxy_mode, self.proxy_url, environment={})

    def public_dict(self) -> dict[str, Any]:
        return {
            "tasks_directory": str(self.tasks_directory),
            "output_directory": str(self.output_directory),
            "model": self.model.public_dict(),
            "image": self.image,
            "image_id": self.image_id,
            "image_digest": self.image_digest,
            "resolved_image": self.resolved_image,
            "proxy_mode": self.proxy_mode.value,
            "budget": asdict(self.budget),
            "engines": [engine.value for engine in self.engines],
            "task_ids": list(self.task_ids),
            "repeats": self.repeats,
        }

    @property
    def resolved_image(self) -> str:
        """Image reference used by both engines after Stage 0 resolution."""

        return self.image_id or self.image_digest or self.image


@dataclass(frozen=True)
class BenchmarkPreflight:
    """No-model Docker checks for one paired benchmark invocation."""

    status: str
    image: str
    resolved_image: str | None
    image_id: str | None
    image_digest: str | None
    checks: tuple[dict[str, Any], ...]
    error: str | None = None

    @property
    def ready(self) -> bool:
        return self.status == "READY"

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "image": self.image,
            "resolved_image": self.resolved_image,
            "image_id": self.image_id,
            "image_digest": self.image_digest,
            "checks": list(self.checks),
            "error": self.error,
        }


BenchmarkPreflightRunner = Callable[[BenchmarkConfig], BenchmarkPreflight]


def preflight_benchmark_image(
    config: BenchmarkConfig,
    *,
    command_runner: Callable[[list[str], float], subprocess.CompletedProcess[str]] | None = None,
) -> BenchmarkPreflight:
    """Resolve and validate the Docker image before any model is created.

    ``docker image inspect`` supplies a content-addressed local image ID.  The
    ID is used for both engines so a mutable tag cannot change between the
    baseline and RepoPilot attempts.  A registry RepoDigest is retained when
    Docker reports one, but locally built images need not have one.
    """

    run_command = command_runner or _run_benchmark_command
    docker = os.environ.get("MSWEA_DOCKER_EXECUTABLE", "docker")
    checks: list[dict[str, Any]] = []
    proxy_args: list[str]
    try:
        proxy_args = docker_proxy_run_args(config.proxy_mode, config.proxy_url)
    except (TypeError, ValueError) as error:
        return BenchmarkPreflight("ENVIRONMENT_UNAVAILABLE", config.image, None, None, None, (), str(error))
    proxy_secrets = _benchmark_secret_values(config)

    # Restrict inspect output to identity fields. Full image metadata may
    # contain build environment details and is not useful benchmark evidence.
    inspect_argv = [
        docker,
        "image",
        "inspect",
        '--format={"Id":{{json .Id}},"RepoDigests":{{json .RepoDigests}}}',
        config.image,
    ]
    inspected, inspect_error = _run_preflight_check(
        "image_inspect", inspect_argv, config.budget.command_timeout_seconds, run_command, proxy_secrets
    )
    checks.append(inspected)
    if inspect_error is not None or inspected["exit_code"] != 0:
        detail = inspect_error or inspected.get("stderr") or "Docker image is not available locally."
        return BenchmarkPreflight(
            "ENVIRONMENT_UNAVAILABLE",
            config.image,
            None,
            None,
            None,
            tuple(checks),
            _redact_benchmark_value(str(detail), proxy_secrets),
        )

    try:
        image_id, image_digest = _parse_image_inspection(inspected.get("stdout", ""))
    except ValueError as error:
        return BenchmarkPreflight("ENVIRONMENT_UNAVAILABLE", config.image, None, None, None, tuple(checks), str(error))

    for command_name, command in (
        ("python", "python --version"),
        ("git", "git --version"),
    ):
        argv = [docker, "run", "--rm", "--pull=never", *proxy_args, image_id, *command.split()]
        check, check_error = _run_preflight_check(
            command_name, argv, config.budget.command_timeout_seconds, run_command, proxy_secrets
        )
        checks.append(check)
        if check_error is not None or check["exit_code"] != 0:
            detail = check_error or check.get("stderr") or f"Docker image does not provide {command.split()[0]}."
            return BenchmarkPreflight(
                "ENVIRONMENT_UNAVAILABLE",
                config.image,
                image_id,
                image_id,
                image_digest,
                tuple(checks),
                _redact_benchmark_value(str(detail), proxy_secrets),
            )

    return BenchmarkPreflight("READY", config.image, image_id, image_id, image_digest, tuple(checks))


def _run_benchmark_command(argv: list[str], timeout: float) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, capture_output=True, check=False, text=True, timeout=timeout)


def _run_preflight_check(
    name: str,
    argv: list[str],
    timeout: float,
    command_runner: Callable[[list[str], float], subprocess.CompletedProcess[str]],
    secrets: Sequence[str],
) -> tuple[dict[str, Any], str | None]:
    started = time.monotonic()
    error: str | None = None
    try:
        completed = command_runner(argv, timeout)
        stdout = _text(completed.stdout)
        stderr = _text(completed.stderr)
        exit_code = completed.returncode
    except subprocess.TimeoutExpired as exception:
        stdout = _text(exception.stdout)
        stderr = _text(exception.stderr)
        exit_code = -1
        error = f"Command timed out after {timeout} seconds."
    except (OSError, subprocess.SubprocessError) as exception:
        stdout = ""
        stderr = str(exception)
        exit_code = -1
        error = str(exception) or type(exception).__name__
    check = {
        "name": name,
        "command": _redact_benchmark_value(argv, secrets),
        "exit_code": exit_code,
        "stdout": _redact_benchmark_value(stdout, secrets),
        "stderr": _redact_benchmark_value(stderr, secrets),
        "duration_seconds": time.monotonic() - started,
    }
    return check, error


def _redact_preflight_result(preflight: BenchmarkPreflight, config: BenchmarkConfig) -> BenchmarkPreflight:
    try:
        secrets = _benchmark_secret_values(config)
    except (TypeError, ValueError):
        secrets = []
    return replace(
        preflight,
        checks=tuple(_redact_benchmark_value(check, secrets) for check in preflight.checks),
        error=_redact_benchmark_value(preflight.error, secrets),
    )


def _parse_image_inspection(output: str) -> tuple[str, str | None]:
    try:
        payload = json.loads(output)
    except (TypeError, json.JSONDecodeError) as error:
        raise ValueError("Docker image inspection returned invalid JSON.") from error
    if isinstance(payload, list):
        payload = payload[0] if payload else None
    if not isinstance(payload, Mapping):
        raise ValueError("Docker image inspection returned no image metadata.")
    image_id = payload.get("Id", payload.get("ID"))
    if not isinstance(image_id, str) or not image_id.strip():
        raise ValueError("Docker image inspection returned no immutable image ID.")
    image_id = image_id.strip()
    repo_digests = payload.get("RepoDigests")
    image_digest = (
        next(
            (value.strip() for value in repo_digests if isinstance(value, str) and value.strip()),
            None,
        )
        if isinstance(repo_digests, list)
        else None
    )
    return image_id, image_digest


@dataclass(frozen=True)
class EngineRequest:
    """Input at the injectable engine executor seam."""

    engine: BenchmarkEngine
    task: BenchmarkTask
    workspace: Path
    artifact_directory: Path
    config: BenchmarkConfig
    initial_head: str | None
    budget: BenchmarkBudget | None = None

    @property
    def effective_budget(self) -> BenchmarkBudget:
        """Return the task override or shared benchmark budget for this request."""

        return self.budget or _effective_budget(self.config, self.task)


@dataclass
class EngineRun:
    """Raw output returned by an engine executor before post-run normalization."""

    status: str | None = None
    duration_seconds: float | None = None
    trajectory: dict[str, Any] | None = None
    run_result: AgentRunResult | None = None
    model_stats: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    evaluation_events: list[dict[str, Any]] = field(default_factory=list)


class EngineExecutor(Protocol):
    def __call__(self, request: EngineRequest) -> EngineRun: ...


@dataclass(frozen=True)
class BenchmarkResult:
    task_id: str
    engine: BenchmarkEngine
    artifact_directory: Path
    status: str | None
    success: bool | None
    metrics: dict[str, Any]
    verifier: dict[str, Any] | None
    error: str | None = None
    evaluation: dict[str, Any] = field(default_factory=dict)
    category: str = "simple"
    capabilities: tuple[str, ...] = ()
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    repeat: int = 1
    model: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "repeat": self.repeat,
            "model": self.model,
            "category": self.category,
            "capabilities": list(self.capabilities),
            "evaluation": self.evaluation,
            "repository_pass": self.evaluation.get("repository_pass", self.success),
            "behavior_pass": self.evaluation.get("behavior_pass"),
            "task_pass": self.evaluation.get("task_pass"),
            "task_id": self.task_id,
            "engine": self.engine.value,
            "artifact_directory": str(self.artifact_directory),
            "status": self.status,
            "success": self.success,
            "metrics": self.metrics,
            "verifier": self.verifier,
            "error": self.error,
        }


@dataclass(frozen=True)
class BenchmarkRun:
    config: BenchmarkConfig
    tasks: tuple[BenchmarkTask, ...]
    results: tuple[BenchmarkResult, ...]
    output_directory: Path

    def to_dict(self) -> dict[str, Any]:
        return {
            "config": self.config.public_dict(),
            "pricing_basis": {
                "tier": "standard",
                "as_of": OPENAI_STANDARD_PRICING_AS_OF,
                "source": OPENAI_STANDARD_PRICING_SOURCE,
                "note": "Estimate only; not provider or intermediary invoice data.",
            },
            "tasks": [_task_public_dict(task) for task in self.tasks],
            "results": [result.to_dict() for result in self.results],
            "evaluation_summary": aggregate([result.to_dict() for result in self.results]),
        }


class BenchmarkRunner:
    """Run fixed tasks in deterministic engine order with replaceable executors."""

    def __init__(
        self,
        config: BenchmarkConfig,
        *,
        executors: Mapping[BenchmarkEngine | str, EngineExecutor] | None = None,
        preflight_runner: BenchmarkPreflightRunner | None = None,
    ):
        self.config = config
        # Injectable executors are the benchmark test seam and stand in for
        # Docker, so they do not require a host Docker daemon. Production runs
        # (or an explicit preflight runner) always execute Stage 0.
        injected_engines = {_coerce_engine(engine) for engine in (executors or {})}
        selected_engines = {_coerce_engine(engine) for engine in config.engines}
        self._run_preflight = preflight_runner is not None or not selected_engines.issubset(injected_engines)
        self._preflight_runner = preflight_runner
        self._executors: dict[BenchmarkEngine, EngineExecutor] = {
            BenchmarkEngine.BASELINE: _run_baseline,
            BenchmarkEngine.REPOPILOT: _run_repopilot,
        }
        for engine, executor in (executors or {}).items():
            self._executors[_coerce_engine(engine)] = executor
        missing = selected_engines - self._executors.keys()
        if missing:
            raise ValueError(f"No registered executor for engines: {sorted(missing)}")

    def load_tasks(self) -> tuple[BenchmarkTask, ...]:
        tasks = load_tasks(self.config.tasks_directory)
        if not self.config.task_ids:
            return tasks
        by_id = {task.task_id: task for task in tasks}
        missing = [task_id for task_id in self.config.task_ids if task_id not in by_id]
        if missing:
            raise ValueError(f"Unknown benchmark task IDs: {', '.join(missing)}")
        return tuple(by_id[task_id] for task_id in self.config.task_ids)

    def run(self) -> BenchmarkRun:
        tasks = self.load_tasks()
        output_directory = self.config.output_directory.resolve()
        if (output_directory / "config.json").exists():
            raise FileExistsError(f"Refusing to overwrite benchmark configuration: {output_directory}")
        output_directory.mkdir(parents=True, exist_ok=True)
        preflight = self._resolve_preflight()
        image_id = preflight.image_id
        if image_id is None and preflight.ready:
            image_id = preflight.resolved_image
        self.config = replace(
            self.config,
            image_id=image_id,
            image_digest=preflight.image_digest,
        )
        (output_directory / "config.json").write_text(
            json.dumps(self.config.public_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        (output_directory / "preflight.json").write_text(
            json.dumps(preflight.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        results: list[BenchmarkResult] = []
        for task in tasks:
            actual_sha = canonical_snapshot_sha256(task.snapshot)
            if actual_sha != task.snapshot_sha256:
                raise ValueError(
                    f"Snapshot SHA256 mismatch for {task.task_id}: expected {task.snapshot_sha256}, got {actual_sha}"
                )
            for repeat in range(1, self.config.repeats + 1):
                trial_directory = (
                    output_directory if self.config.repeats == 1 else output_directory / f"repeat-{repeat:03d}"
                )
                for engine in self.config.engines:
                    results.append(self._run_one(task, _coerce_engine(engine), trial_directory, preflight, repeat))

        benchmark_run = BenchmarkRun(self.config, tasks, tuple(results), output_directory)
        (output_directory / "summary.json").write_text(
            json.dumps(benchmark_run.to_dict(), indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8"
        )
        (output_directory / "summary.md").write_text(_summary_markdown(benchmark_run), encoding="utf-8")
        return benchmark_run

    def _resolve_preflight(self) -> BenchmarkPreflight:
        if not self._run_preflight:
            return BenchmarkPreflight(
                "READY",
                self.config.image,
                self.config.resolved_image,
                self.config.image_id,
                self.config.image_digest,
                (),
            )
        try:
            if self._preflight_runner is not None:
                preflight = self._preflight_runner(self.config)
            else:
                preflight = preflight_benchmark_image(self.config)
            return _redact_preflight_result(preflight, self.config)
        except Exception as exception:
            error = str(exception) or type(exception).__name__
            try:
                error = _redact_benchmark_value(error, _benchmark_secret_values(self.config))
            except (TypeError, ValueError):
                pass
            return BenchmarkPreflight(
                "ENVIRONMENT_UNAVAILABLE",
                self.config.image,
                None,
                None,
                None,
                (),
                error,
            )

    def _run_one(
        self,
        task: BenchmarkTask,
        engine: BenchmarkEngine,
        output_directory: Path,
        preflight: BenchmarkPreflight | None = None,
        repeat: int = 1,
    ) -> BenchmarkResult:
        task_directory = output_directory / task.task_id / engine.value
        if task_directory.exists():
            raise FileExistsError(f"Refusing to overwrite trial artifacts: {task_directory}")
        task_directory.mkdir(parents=True, exist_ok=True)
        workspace = task_directory / "workspace"
        copy_snapshot(task.snapshot, workspace)
        initial_head = initialize_git_snapshot(workspace)
        if preflight is not None:
            (task_directory / "preflight.json").write_text(
                json.dumps(preflight.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
        request = EngineRequest(
            engine,
            task,
            workspace,
            task_directory,
            self.config,
            initial_head,
            _effective_budget(self.config, task),
        )
        started = time.monotonic()
        error: str | None = None
        if preflight is not None and not preflight.ready:
            # Stage 0 failures become paired results without constructing a
            # model or entering either paid Agent Run executor.
            run = EngineRun(status="ENVIRONMENT_UNAVAILABLE", error=preflight.error)
        else:
            try:
                run = self._executors[engine](request)
            except Exception as exception:  # executor failures are benchmark results, not runner crashes
                status = (
                    "ENVIRONMENT_UNAVAILABLE"
                    if isinstance(exception, (FileNotFoundError, subprocess.CalledProcessError))
                    else None
                )
                run = EngineRun(status=status, error=str(exception) or type(exception).__name__)
        secrets = _benchmark_secret_values(self.config)
        run.status = _redact_benchmark_value(run.status, secrets)
        run.error = _redact_benchmark_value(run.error, secrets)
        run.trajectory = _redact_benchmark_value(run.trajectory, secrets)
        run.model_stats = _redact_benchmark_value(run.model_stats, secrets)
        _redact_benchmark_artifacts(task_directory, secrets)
        if run.duration_seconds is None:
            run.duration_seconds = time.monotonic() - started
        if run.error is not None:
            error = run.error

        patch = capture_patch(workspace, initial_head)
        patch_path = task_directory / "patch.diff"
        patch_path.write_text(patch or "", encoding="utf-8")
        commits = capture_commits(workspace, initial_head)
        verifier = None if run.status == "ENVIRONMENT_UNAVAILABLE" else run_hidden_verifier(task, workspace)
        verifier = _redact_benchmark_value(verifier, secrets)
        success = None if verifier is None else verifier.get("exit_code") == 0
        metrics = _redact_benchmark_value(
            _metrics_for_run(
                engine,
                run,
                task_directory,
                patch,
                commits,
                verifier,
                model_name=self.config.model.model_name,
            ),
            secrets,
        )
        metrics["run_budget"] = asdict(request.effective_budget)
        metrics["image"] = self.config.resolved_image
        metrics["image_id"] = self.config.image_id
        metrics["image_digest"] = self.config.image_digest
        if preflight is not None:
            metrics["preflight"] = preflight.to_dict()
        error = _redact_benchmark_value(error, secrets)
        trace = _read_trace(task_directory / "trace.jsonl")
        events = normalize_trace(trace) + run.evaluation_events
        metrics["llm_calls"] = (
            sum(e.get("type") == "model_request" for e in trace) if trace else run.model_stats.get("steps")
        )
        evaluation = evaluate(success, run.status, metrics, events, task.behavior_requirements)
        metrics["tool_failures"] = evaluation["tool_quality"]["failure_count"]
        if engine is BenchmarkEngine.BASELINE and metrics["tool_failures"] is None:
            errors = metrics.get("errors")
            if isinstance(errors, list):
                metrics["tool_failures"] = sum(e.get("type") == "command" for e in errors)
                evaluation["tool_quality"]["failure_count"] = metrics["tool_failures"]
                count = metrics.get("tool_calls")
                evaluation["tool_quality"]["failure_rate"] = metrics["tool_failures"] / count if count else None
        evaluation = _redact_benchmark_value(evaluation, secrets)
        (task_directory / "evaluation-events.json").write_text(
            json.dumps(_redact_benchmark_value(events, secrets), indent=2) + "\n", encoding="utf-8"
        )
        if task.behavior_verifier_path is not None and verifier is not None:
            evaluation = _run_behavior_verifier(task, task_directory, evaluation, secrets)
        result = BenchmarkResult(
            task.task_id,
            engine,
            task_directory,
            run.status,
            success,
            metrics,
            verifier,
            error,
            evaluation=evaluation,
            category=task.category,
            capabilities=task.capabilities,
            repeat=repeat,
            model=self.config.model.model_name,
        )
        (task_directory / "result.json").write_text(
            json.dumps(result.to_dict(), indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8"
        )
        return result


def load_task_manifest(manifest_path: Path) -> BenchmarkTask:
    """Load and normalize one manifest."""

    return BenchmarkTask.from_manifest(manifest_path.resolve())


def load_tasks(tasks_directory: Path) -> tuple[BenchmarkTask, ...]:
    """Load manifests in lexical task order."""

    root = tasks_directory.resolve()
    if root.is_file() and root.name == "manifest.json":
        manifests = [root]
    else:
        manifests = sorted(root.glob("*/manifest.json"))
    if not manifests:
        raise FileNotFoundError(f"No benchmark task manifests found under {root}")
    return tuple(load_task_manifest(path) for path in manifests)


def canonical_snapshot_sha256(snapshot: Path) -> str:
    """Hash a snapshot while ignoring source-control and Python-generated files."""

    root = snapshot.resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"Benchmark snapshot does not exist: {root}")
    digest = hashlib.sha256()
    paths = sorted(path for path in root.rglob("*") if path.is_file() and not _is_ignored_snapshot_path(path, root))
    for path in paths:
        relative = path.relative_to(root).as_posix().encode()
        digest.update(relative)
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def copy_snapshot(snapshot: Path, workspace: Path) -> None:
    """Copy a clean snapshot without source-control or Python-generated files."""

    root = snapshot.resolve()

    def ignore(directory: str, names: list[str]) -> set[str]:
        return {name for name in names if _is_ignored_snapshot_path((Path(directory) / name).resolve(), root)}

    shutil.copytree(root, workspace, ignore=ignore)


def _is_ignored_snapshot_path(path: Path, root: Path) -> bool:
    """Return whether a path is generated metadata excluded from a snapshot."""

    relative = path.relative_to(root)
    return ".git" in relative.parts or "__pycache__" in relative.parts or path.suffix in {".pyc", ".pyo"}


def initialize_git_snapshot(workspace: Path) -> str | None:
    """Create the fixed initial commit used for patch and commit accounting."""

    _run_git(workspace, ["init", "-q", "--initial-branch=main"])
    _run_git(workspace, ["config", "user.name", "RepoPilot Benchmark"])
    _run_git(workspace, ["config", "user.email", "benchmark@repopilot.invalid"])
    _run_git(workspace, ["add", "--all"])
    fixed_git_dates = {
        "GIT_AUTHOR_DATE": "2000-01-01T00:00:00+00:00",
        "GIT_COMMITTER_DATE": "2000-01-01T00:00:00+00:00",
    }
    _run_git(
        workspace,
        ["commit", "--quiet", "--allow-empty", "--message", "benchmark seed snapshot"],
        env=fixed_git_dates,
    )
    return _git_head(workspace)


def run_benchmark(
    config: BenchmarkConfig,
    *,
    executors: Mapping[BenchmarkEngine | str, EngineExecutor] | None = None,
    preflight_runner: BenchmarkPreflightRunner | None = None,
) -> BenchmarkRun:
    """Convenience entry point for the benchmark runner."""

    return BenchmarkRunner(config, executors=executors, preflight_runner=preflight_runner).run()


def _effective_budget(config: BenchmarkConfig, task: BenchmarkTask) -> BenchmarkBudget:
    """Apply the shared invocation budget, then task manifest overrides.

    The shared CLI/invocation budget is the base for every task.  A manifest
    ``run_budget`` overrides only the fields it explicitly declares (documented
    as "the manifest budget overrides benchmark defaults"), so a task that
    declares a larger step/wall-clock ceiling keeps the shared command timeout
    and consecutive-failure policy.  Every Agent Run is then capped by the
    task's own timeout so a permissive manifest cannot exceed it.
    """

    configured = config.budget
    declared = task.run_budget_declared
    task_budget = task.run_budget
    if not declared or task_budget is None:
        merged = configured
    else:
        kwargs: dict[str, Any] = {
            "max_steps": configured.max_steps,
            "max_replans": configured.max_replans,
            "max_consecutive_failures": configured.max_consecutive_failures,
            "command_timeout_seconds": configured.command_timeout_seconds,
            "max_run_seconds": configured.max_run_seconds,
        }
        for destination in declared:
            kwargs[destination] = getattr(task_budget, destination)
        merged = BenchmarkBudget(**kwargs)
    max_run_seconds = min(merged.max_run_seconds, task.timeout_seconds)
    return BenchmarkBudget(
        max_steps=merged.max_steps,
        max_replans=merged.max_replans,
        max_consecutive_failures=merged.max_consecutive_failures,
        command_timeout_seconds=merged.command_timeout_seconds,
        max_run_seconds=max_run_seconds,
    )


def _run_baseline(request: EngineRequest) -> EngineRun:
    config = request.config
    benchmark_budget = request.effective_budget
    run_budget = benchmark_budget.to_run_budget()
    trajectory_path = request.artifact_directory / "trajectory.json"
    model_kwargs = dict(config.model.model_kwargs)
    if config.model.api_key is not None:
        model_kwargs["api_key"] = config.model.api_key
    if config.model.base_url is not None:
        model_kwargs["api_base"] = config.model.base_url
    model_config: dict[str, Any] = {
        "model_name": config.model.model_name,
        "model_kwargs": model_kwargs,
        "cost_tracking": "ignore_errors",
    }
    if model_kwargs.get("stream"):
        # Some OpenAI-compatible intermediaries restrict an account to
        # streaming-only requests.  Point the baseline at RepoPilot's streaming
        # subclass instead of the vendored non-streaming LitellmModel.
        model_config["model_class"] = "repopilot.litellm_streaming.StreamingLitellmModel"
    model = get_model(config=model_config)
    run_args = [
        "--rm",
        "--mount",
        f"type=bind,source={request.workspace.resolve()},target=/workspace",
    ]
    if host_identity := _host_identity():
        run_args.append(f"--user={host_identity}")
    environment_config = {
        "environment_class": "docker",
        "image": config.resolved_image,
        "cwd": "/workspace",
        "run_args": run_args + docker_proxy_run_args(config.proxy_mode, config.proxy_url),
        "timeout": max(1, int(run_budget.command_timeout_seconds)),
    }
    environment = ScenarioObserver(
        get_environment(environment_config, default_type="docker"), request.workspace, request.task.behavior_spec
    )
    agent_config = recursive_merge(
        get_config_from_spec(builtin_config_dir / "mini.yaml").get("agent", {}),
        {
            "step_limit": run_budget.max_steps,
            "wall_time_limit_seconds": max(1, int(run_budget.max_run_seconds)),
            "cost_limit": 0,
            # Upstream saves on every step.  Keep that intermediate serialization
            # in memory so the benchmark seam can redact it before persistence.
            "output_path": None,
        },
    )
    agent = get_agent(model, environment, agent_config, default_type="default")
    started = time.monotonic()
    info: dict[str, Any] = {}
    error: str | None = None
    try:
        value = agent.run(request.task.task)
        if isinstance(value, dict):
            info = value
    except Exception as exception:
        error = str(exception) or type(exception).__name__
    finally:
        raw_trajectory = agent.save(None, {"benchmark": {"engine": BenchmarkEngine.BASELINE.value}})
        trajectory = _redact_benchmark_value(raw_trajectory, _benchmark_secret_values(config))
        trajectory_path.parent.mkdir(parents=True, exist_ok=True)
        trajectory_path.write_text(json.dumps(trajectory, indent=2), encoding="utf-8")
        _cleanup_baseline_environment(environment)
    return EngineRun(
        status=info.get("exit_status") or _trajectory_status(trajectory),
        duration_seconds=time.monotonic() - started,
        trajectory=trajectory,
        model_stats=_baseline_model_stats(trajectory),
        evaluation_events=environment.events + [scenario_audit(request.task.behavior_spec)],
        error=_redact_benchmark_value(error, _benchmark_secret_values(config)),
    )


class _BenchmarkToolCallingModel(LiteLLMToolCallingModel):
    """RepoPilot's model adapter with benchmark-only parameter/stat accounting."""

    def __init__(self, *, model: BenchmarkModel):
        super().__init__(
            model_name=model.model_name,
            api_key=model.api_key,
            base_url=model.base_url,
            model_kwargs=model.model_kwargs,
        )
        self.calls = 0
        self.prompt_tokens: int | None = None
        self.completion_tokens: int | None = None
        self.total_tokens: int | None = None
        self.cached_tokens: int | None = None
        self.cache_write_tokens: int | None = None
        self.reasoning_tokens: int | None = None
        self.cost: float | None = None
        self._saw_usage = False
        self._usage_missing: dict[str, bool] = {
            "prompt_tokens": False,
            "completion_tokens": False,
            "total_tokens": False,
            "cached_tokens": False,
            "cache_write_tokens": False,
            "reasoning_tokens": False,
        }
        self._saw_cost = False

    def complete(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> AssistantTurn:
        turn = super().complete(messages, tools)
        self.calls += 1
        usage = turn.usage
        self._saw_usage = True
        for attribute, key in (
            ("prompt_tokens", "prompt_tokens"),
            ("completion_tokens", "completion_tokens"),
            ("total_tokens", "total_tokens"),
            ("cached_tokens", "cached_tokens"),
            ("cache_write_tokens", "cache_write_tokens"),
            ("reasoning_tokens", "reasoning_tokens"),
        ):
            value = usage.get(key) if usage is not None else None
            if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                if not self._usage_missing[key]:
                    setattr(self, attribute, (getattr(self, attribute) or 0) + value)
            else:
                # A partial provider usage response cannot be safely summed;
                # preserve null for that aggregate instead of implying a
                # complete count.
                self._usage_missing[key] = True
        cost_value = turn.cost
        if isinstance(cost_value, (float, int)) and not isinstance(cost_value, bool):
            self._saw_cost = True
            self.cost = (self.cost or 0.0) + float(cost_value)
        return turn

    def stats(self) -> dict[str, Any]:
        return {
            "steps": self.calls,
            "tokens": {
                "prompt": self.prompt_tokens if self._saw_usage and not self._usage_missing["prompt_tokens"] else None,
                "completion": self.completion_tokens
                if self._saw_usage and not self._usage_missing["completion_tokens"]
                else None,
                "total": self.total_tokens if self._saw_usage and not self._usage_missing["total_tokens"] else None,
                "cached": self.cached_tokens if self._saw_usage and not self._usage_missing["cached_tokens"] else None,
                "cache_write": self.cache_write_tokens
                if self._saw_usage and not self._usage_missing["cache_write_tokens"]
                else None,
                "reasoning": self.reasoning_tokens
                if self._saw_usage and not self._usage_missing["reasoning_tokens"]
                else None,
            },
            "cost": self.cost if self._saw_cost else None,
        }


def _run_repopilot(request: EngineRequest) -> EngineRun:
    config = request.config
    model = _BenchmarkToolCallingModel(model=config.model)
    environment = DockerExecutionEnvironment(
        request.workspace,
        image=config.resolved_image,
        proxy_mode=config.proxy_mode,
        proxy_url=config.proxy_url,
    )
    environment = ScenarioObserver(environment, request.workspace, request.task.behavior_spec)
    state_directory = request.artifact_directory / "run-state"
    artifacts = RunArtifacts(state_directory, secrets=_benchmark_secret_values(config))
    plan_history = PlanHistory.for_task(request.task.task)
    budget = request.effective_budget.to_run_budget()
    runtime = AgentRuntime(
        model,
        create_tool_registry(
            environment,
            request.workspace,
            plan_history,
            command_timeout_seconds=budget.command_timeout_seconds,
        ),
        artifacts,
        plan_history,
        budget,
        checkpoint_model={
            "backend": "litellm",
            "model_name": config.model.model_name,
            "model_kwargs": {key: value for key, value in config.model.model_kwargs.items() if key != "api_key"},
            "base_url": config.model.base_url,
        },
        checkpoint_environment={"backend": "docker", "image": config.resolved_image},
        context=ContextManager(),
        approval_context=ApprovalContext(
            environment="docker", disposable_benchmark=True, automatic_approval=request.task.category != "hitl"
        ),
    )
    started = time.monotonic()
    result: AgentRunResult | None = None
    error: str | None = None
    try:
        result = runtime.run(request.task.task, request.workspace)
        approvals = 0
        while (
            result.status == "WAITING_FOR_APPROVAL"
            and approvals < budget.max_steps
            and time.monotonic() - started < budget.max_run_seconds
        ):
            approvals += 1
            result = runtime.run(
                request.task.task,
                request.workspace,
                checkpoint=artifacts.read_checkpoint(),
                approval_granted=request.task.approval_policy == "approve",
            )
    except Exception as exception:
        error = str(exception) or type(exception).__name__
    finally:
        environment.close()
    if artifacts.path.is_dir():
        _copy_runtime_artifacts(artifacts.path, request.artifact_directory)
    return EngineRun(
        status=result.status if result is not None else None,
        duration_seconds=time.monotonic() - started,
        run_result=result,
        model_stats=model.stats(),
        evaluation_events=environment.events + [scenario_audit(request.task.behavior_spec)],
        error=_redact_benchmark_value(error, _benchmark_secret_values(config)),
    )


def _copy_runtime_artifacts(source: Path, destination: Path) -> None:
    for path in source.iterdir():
        if path.name == "result.json":
            continue
        target = destination / path.name
        if path.is_file():
            shutil.copy2(path, target)


def _benchmark_secret_values(config: BenchmarkConfig) -> list[str]:
    model = config.model
    values: list[str] = []
    for candidate in (
        model.api_key,
        model.base_url,
        model.model_kwargs.get("api_key"),
        model.model_kwargs.get("api_base"),
        model.model_kwargs.get("base_url"),
    ):
        if isinstance(candidate, str) and candidate and candidate not in values:
            values.append(candidate)
    if config.proxy_url and config.proxy_url not in values:
        values.append(config.proxy_url)
    for argument in docker_proxy_run_args(config.proxy_mode, config.proxy_url):
        name, separator, value = argument.partition("=")
        if separator and name.upper() in {"HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"} and value not in values:
            values.append(value)
    return values


def _redact_benchmark_value(value: Any, secrets: Sequence[str]) -> Any:
    if isinstance(value, str):
        redacted = value
        for secret in secrets:
            redacted = redacted.replace(secret, "[REDACTED]")
        return redacted
    if isinstance(value, dict):
        return {
            _redact_benchmark_value(key, secrets): _redact_benchmark_value(item, secrets) for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact_benchmark_value(item, secrets) for item in value]
    if isinstance(value, tuple):
        return tuple(_redact_benchmark_value(item, secrets) for item in value)
    return value


def _redact_benchmark_artifacts(directory: Path, secrets: Sequence[str]) -> None:
    if not secrets:
        return
    for path in directory.rglob("*"):
        if not path.is_file() or "workspace" in path.relative_to(directory).parts:
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        redacted = _redact_benchmark_value(content, secrets)
        if redacted != content:
            path.write_text(redacted, encoding="utf-8")


def run_hidden_verifier(task: BenchmarkTask, workspace: Path) -> dict[str, Any] | None:
    """Run the manifest verifier on the host after the engine has stopped."""

    started = time.monotonic()
    timeout_seconds = (
        task.verifier_timeout_seconds if task.verifier_timeout_seconds is not None else task.timeout_seconds
    )
    if task.verifier_path is not None:
        command = [sys.executable, str(task.verifier_path.resolve()), str(workspace.resolve())]
    elif task.verifier_command:
        command = ["bash", "-lc", task.verifier_command]
    else:
        return None
    try:
        completed = subprocess.run(
            command,
            cwd=workspace,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_seconds,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )
        return {
            "exit_code": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "duration_seconds": time.monotonic() - started,
            "success_condition": task.success_condition,
        }
    except subprocess.TimeoutExpired as exception:
        return {
            "exit_code": -1,
            "stdout": _text(exception.stdout),
            "stderr": _text(exception.stderr) or f"Verifier timed out after {timeout_seconds} seconds.",
            "duration_seconds": time.monotonic() - started,
            "success_condition": task.success_condition,
            "timed_out": True,
        }
    except OSError as exception:
        return {
            "exit_code": -1,
            "stdout": "",
            "stderr": str(exception),
            "duration_seconds": time.monotonic() - started,
            "success_condition": task.success_condition,
        }


def capture_patch(workspace: Path, initial_head: str | None) -> str | None:
    if initial_head is None:
        return None
    tracked = subprocess.run(
        [
            "git",
            "diff",
            "--no-ext-diff",
            "--binary",
            initial_head,
            "--",
            ".",
            ":(exclude,glob)**/__pycache__/**",
            ":(exclude,glob)**/*.pyc",
            ":(exclude,glob)**/*.pyo",
        ],
        cwd=workspace,
        capture_output=True,
        text=True,
        check=False,
    ).stdout
    untracked = _run_git(workspace, ["ls-files", "--others", "--exclude-standard", "-z"], check=False)
    chunks = [tracked]
    for relative in untracked.decode(errors="surrogateescape").split("\0"):
        if not relative:
            continue
        if _is_ignored_snapshot_path((workspace / relative).resolve(), workspace.resolve()):
            continue
        result = subprocess.run(
            ["git", "diff", "--no-index", "--binary", "/dev/null", relative],
            cwd=workspace,
            capture_output=True,
            text=True,
            check=False,
        )
        chunks.append(result.stdout)
    return "".join(chunks)


def capture_commits(workspace: Path, initial_head: str | None) -> list[dict[str, str]] | None:
    if initial_head is None:
        return None
    output = _run_git(workspace, ["log", "--format=%H%x00%s", f"{initial_head}..HEAD"], check=False)
    commits: list[dict[str, str]] = []
    for line in output.decode(errors="replace").splitlines():
        commit_hash, separator, message = line.partition("\0")
        if separator:
            commits.append({"hash": commit_hash, "message": message})
    return commits


def _metrics_for_run(
    engine: BenchmarkEngine,
    run: EngineRun,
    artifact_directory: Path,
    patch: str | None,
    commits: list[dict[str, str]] | None,
    verifier: dict[str, Any] | None,
    *,
    model_name: str | None = None,
) -> dict[str, Any]:
    if engine is not BenchmarkEngine.REPOPILOT:
        trajectory = run.trajectory or {}
        tokens = run.model_stats.get("tokens")
        return {
            "steps": run.model_stats.get("steps"),
            "tokens": tokens,
            "cost": run.model_stats.get("cost"),
            "openai_standard_estimated_cost_usd": _estimated_standard_cost(model_name, tokens),
            "tool_calls": run.model_stats.get("tool_calls"),
            "errors": run.model_stats.get("errors"),
            "retries": None,
            "replans": None,
            "duration_seconds": run.duration_seconds,
            "patch": _patch_metric(artifact_directory / "patch.diff", patch),
            "commits": commits,
            "trajectory_status": _trajectory_status(trajectory),
        }
    metadata = _read_json(artifact_directory / "metadata.json")
    trace = _read_trace(artifact_directory / "trace.jsonl")
    recoveries = metadata.get("recoveries", []) if isinstance(metadata.get("recoveries"), list) else []
    failures = metadata.get("failures", []) if isinstance(metadata.get("failures"), list) else []
    retries = sum(1 for item in recoveries if isinstance(item, dict) and item.get("action") == "RETRY_MODEL")
    budget = metadata.get("budget", {}) if isinstance(metadata.get("budget"), dict) else {}
    tokens = run.model_stats.get("tokens")
    return {
        "steps": budget.get("steps_used"),
        "tokens": tokens,
        "cost": run.model_stats.get("cost"),
        "openai_standard_estimated_cost_usd": _estimated_standard_cost(model_name, tokens),
        "tool_calls": sum(1 for event in trace if event.get("type") == "tool_call"),
        "errors": failures,
        "retries": retries,
        "replans": budget.get("replans_used"),
        "duration_seconds": run.duration_seconds,
        "patch": _patch_metric(artifact_directory / "patch.diff", patch),
        "commits": commits,
        "trajectory_status": run.status,
        "verifier_success": None if verifier is None else verifier.get("exit_code") == 0,
    }


def _run_behavior_verifier(task, directory, evaluation, secrets):
    """Run a trusted host-only checker against retained normalized evidence."""
    context_path = directory / "evaluation-context.json"
    context_path.write_text(json.dumps(evaluation, indent=2) + "\n", encoding="utf-8")
    try:
        completed = subprocess.run(
            [sys.executable, str(task.behavior_verifier_path), str(directory)],
            capture_output=True,
            text=True,
            check=False,
            timeout=task.verifier_timeout_seconds or 20,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )
        if completed.returncode != 0:
            raise ValueError(f"Behavior verifier exit {completed.returncode}: {completed.stderr}")
        checks = json.loads(completed.stdout)["checks"]
        for requirement in task.behavior_requirements:
            check = checks[requirement]
            if (
                not isinstance(check, dict)
                or "pass" not in check
                or (check["pass"] is not None and type(check["pass"]) is not bool)
            ):
                raise ValueError(f"Invalid behavior check: {requirement}")
            evaluation["behavior_verifier"][requirement] = check
    except (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired) as error:
        evaluation["behavior_verifier"] = {
            key: {"pass": None, "reason": f"Behavior verifier unavailable: {error}"}
            for key in task.behavior_requirements
        }
    checks = evaluation["behavior_verifier"].values()
    evaluation["behavior_pass"] = (
        False if any(c["pass"] is False for c in checks) else None if any(c["pass"] is None for c in checks) else True
    )
    repository, behavior = evaluation["repository_pass"], evaluation["behavior_pass"]
    evaluation["task_pass"] = (
        False if repository is False or behavior is False else None if repository is None or behavior is None else True
    )
    return _redact_benchmark_value(evaluation, secrets)


def _estimated_standard_cost(model_name: str | None, tokens: Any) -> float | None:
    """Return a labelled OpenAI Standard estimate for aggregated benchmark usage."""

    if not isinstance(model_name, str) or not isinstance(tokens, Mapping):
        return None
    # ``tokens`` is the benchmark's stable public shape.  Adapt it to the
    # pricing seam's provider-shaped usage mapping without changing the
    # existing ``metrics.cost`` provider/LiteLLM meaning.
    usage = {
        "prompt_tokens": tokens.get("prompt"),
        "completion_tokens": tokens.get("completion"),
        "cached_tokens": tokens.get("cached"),
        "cache_write_tokens": tokens.get("cache_write"),
    }
    try:
        value = estimate_openai_standard_cost(model_name, usage)
    except (KeyError, TypeError, ValueError):
        # Custom relay model IDs are expected.  An unavailable catalog price
        # should not make a benchmark run fail or turn into a fake invoice.
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def _baseline_model_stats(trajectory: dict[str, Any]) -> dict[str, Any]:
    info = trajectory.get("info", {}) if isinstance(trajectory, dict) else {}
    stats = info.get("model_stats", {}) if isinstance(info, dict) else {}
    messages = trajectory.get("messages", []) if isinstance(trajectory, dict) else []
    if not isinstance(messages, list):
        messages = []
    usages: list[dict[str, int | None]] = []
    costs: list[float] = []
    actions = 0
    errors: list[dict[str, Any]] = []
    for message in messages:
        if not isinstance(message, dict):
            continue
        extra = message.get("extra")
        if not isinstance(extra, dict):
            continue
        action_value = extra.get("actions")
        if isinstance(action_value, list):
            actions += len(action_value)
        cost = extra.get("cost")
        if isinstance(cost, (int, float)):
            costs.append(float(cost))
        usage = extra.get("response")
        usage_dict = _usage_dict(usage)
        if usage_dict is not None:
            usages.append(usage_dict)
        returncode = extra.get("returncode")
        if isinstance(returncode, int) and returncode != 0:
            errors.append({"type": "command", "returncode": returncode})
        if extra.get("interrupt_type") == "FormatError":
            errors.append({"type": "format", "reason": message.get("content")})
        if extra.get("exception_info"):
            errors.append({"type": "environment", "reason": extra.get("exception_info")})
        if extra.get("exception_str"):
            errors.append({"type": "exception", "reason": extra.get("exception_str")})
    model_stats: dict[str, Any] = {
        "steps": stats.get("api_calls") if isinstance(stats, dict) else None,
        "tokens": _sum_usage(usages),
        "cost": float(stats["instance_cost"])
        if (
            isinstance(stats, dict)
            and isinstance(stats.get("instance_cost"), (int, float))
            and any(cost > 0.0 for cost in costs)
        )
        else None,
        "tool_calls": actions,
        "errors": errors,
    }
    return model_stats


def _sum_usage(usages: Sequence[Mapping[str, int | None]]) -> dict[str, int | None] | None:
    if not usages:
        return {
            "prompt": None,
            "completion": None,
            "total": None,
            "cached": None,
            "cache_write": None,
            "reasoning": None,
        }
    result: dict[str, int | None] = {"prompt": 0, "completion": 0, "total": 0}
    result.update({"cached": 0, "cache_write": 0, "reasoning": 0})
    for usage in usages:
        for destination, source in (
            ("prompt", "prompt_tokens"),
            ("completion", "completion_tokens"),
            ("total", "total_tokens"),
            ("cached", "cached_tokens"),
            ("cache_write", "cache_write_tokens"),
            ("reasoning", "reasoning_tokens"),
        ):
            if result[destination] is None:
                continue
            value = usage.get(source)
            if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                result[destination] = (result[destination] or 0) + value
            else:
                result[destination] = None
    return result


def _usage_dict(response: Any) -> dict[str, int | None] | None:
    if response is None:
        return None
    if isinstance(response, dict):
        usage = response.get("usage", response)
    else:
        usage = getattr(response, "usage", None)
        if usage is None and hasattr(response, "model_dump"):
            try:
                dumped = response.model_dump()
            except Exception:
                dumped = None
            usage = dumped.get("usage") if isinstance(dumped, dict) else None
    if hasattr(usage, "model_dump"):
        usage = usage.model_dump()
    if not isinstance(usage, Mapping):
        return None
    result: dict[str, int | None] = {
        "prompt_tokens": _usage_token(usage, ("prompt_tokens", "input_tokens")),
        "completion_tokens": _usage_token(usage, ("completion_tokens", "output_tokens")),
        "total_tokens": _usage_token(usage, ("total_tokens",)),
        "cached_tokens": _usage_token(
            usage,
            ("cached_tokens", "cache_read_tokens", "cache_read_input_tokens", "cached_input_tokens"),
        ),
        "cache_write_tokens": _usage_token(
            usage,
            ("cache_write_tokens", "cache_write_input_tokens", "cache_creation_input_tokens", "cache_creation_tokens"),
        ),
        "reasoning_tokens": _usage_token(usage, ("reasoning_tokens", "reasoning")),
    }
    return result


def _usage_token(usage: Mapping[str, Any], aliases: Sequence[str]) -> int | None:
    """Read one token count from top-level usage or a provider detail object."""

    for alias in aliases:
        value = usage.get(alias)
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            return value
    for details_key in (
        "prompt_tokens_details",
        "input_tokens_details",
        "prompt_token_details",
        "input_token_details",
        "completion_tokens_details",
        "output_tokens_details",
        "completion_token_details",
        "output_token_details",
    ):
        details = usage.get(details_key)
        if not isinstance(details, Mapping):
            continue
        for alias in aliases:
            value = details.get(alias)
            if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                return value
    return None


def _patch_metric(path: Path, patch: str | None) -> dict[str, Any] | None:
    if patch is None:
        return None
    return {
        "path": str(path),
        "changed": bool(patch),
        "sha256": hashlib.sha256(patch.encode()).hexdigest(),
    }


def _trajectory_status(trajectory: dict[str, Any]) -> str | None:
    info = trajectory.get("info") if isinstance(trajectory, dict) else None
    return info.get("exit_status") if isinstance(info, dict) and isinstance(info.get("exit_status"), str) else None


def _cleanup_baseline_environment(environment: Any) -> None:
    cleanup = getattr(environment, "cleanup", None)
    if callable(cleanup):
        cleanup()
    else:
        close = getattr(environment, "close", None)
        if callable(close):
            close()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, UnicodeDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _read_trace(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    events: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            events.append(value)
    return events


def _run_git(
    workspace: Path,
    arguments: list[str],
    *,
    check: bool = True,
    env: Mapping[str, str] | None = None,
) -> bytes:
    process_environment = None if env is None else {**os.environ, **env}
    result = subprocess.run(
        ["git", *arguments],
        cwd=workspace,
        capture_output=True,
        check=False,
        env=process_environment,
    )
    if check and result.returncode != 0:
        raise RuntimeError(result.stderr.decode(errors="replace").strip() or f"git {' '.join(arguments)} failed")
    return result.stdout


def _git_head(workspace: Path) -> str | None:
    result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=workspace, capture_output=True, text=True, check=False)
    return result.stdout.strip() if result.returncode == 0 else None


def _first_string(value: Mapping[str, Any], *names: str) -> str | None:
    for name in names:
        candidate = value.get(name)
        if isinstance(candidate, str) and candidate:
            return candidate
    return None


def _host_identity() -> str:
    try:
        return f"{os.getuid()}:{os.getgid()}"
    except AttributeError:
        return ""


def _coerce_engine(value: BenchmarkEngine | str) -> BenchmarkEngine:
    if isinstance(value, BenchmarkEngine):
        return value
    try:
        return BenchmarkEngine(value)
    except ValueError:
        if not value or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for c in value):
            raise ValueError("Engine variant must be a nonempty safe identifier") from None
        return EngineVariant(value)


def _text(value: str | bytes | None) -> str:
    if isinstance(value, bytes):
        return value.decode(errors="replace")
    return value or ""


def _task_public_dict(task: BenchmarkTask) -> dict[str, Any]:
    return {
        "task_id": task.task_id,
        "task": task.task,
        "category": task.category,
        "capabilities": list(task.capabilities),
        "behavior_requirements": list(task.behavior_requirements),
        "behavior_spec": task.behavior_spec,
        "behavior_verifier_path": str(task.behavior_verifier_path) if task.behavior_verifier_path else None,
        "approval_policy": task.approval_policy,
        "experimental": task.experimental,
        "snapshot": str(task.snapshot),
        "snapshot_revision": task.snapshot_revision,
        "snapshot_sha256": task.snapshot_sha256,
        "success_condition": task.success_condition,
        "timeout_seconds": task.timeout_seconds,
        "verifier_path": str(task.verifier_path) if task.verifier_path is not None else None,
        "verifier_timeout_seconds": task.verifier_timeout_seconds,
        "run_budget": asdict(task.run_budget) if task.run_budget is not None else None,
        "run_budget_declared": sorted(task.run_budget_declared),
    }


def _summary_markdown(benchmark_run: BenchmarkRun) -> str:
    return (
        markdown(aggregate([result.to_dict() for result in benchmark_run.results]))
        + "\n"
        + _legacy_summary_markdown(benchmark_run)
    )


def _legacy_summary_markdown(benchmark_run: BenchmarkRun) -> str:
    revisions = {task.task_id: task.snapshot_revision for task in benchmark_run.tasks}
    lines = [
        "# Agent Benchmark Summary",
        "",
        "| Task | Snapshot Revision | Engine | Status | Success | Steps | Total tokens | Provider/LiteLLM cost | OpenAI Standard estimate | Duration (s) |",
        "| --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for result in benchmark_run.results:
        metrics = result.metrics
        tokens = metrics.get("tokens")
        total_tokens = tokens.get("total") if isinstance(tokens, Mapping) else None
        cost = metrics.get("cost")
        cost_text = "null" if cost is None else str(cost)
        estimate = metrics.get("openai_standard_estimated_cost_usd")
        estimate_text = "null" if estimate is None else str(estimate)
        duration = metrics.get("duration_seconds")
        duration_text = "null" if duration is None else str(duration)
        lines.append(
            f"| {result.task_id} | {revisions.get(result.task_id) or 'null'} | {result.engine.value} | "
            f"{result.status or 'null'} | "
            f"{str(result.success).lower() if result.success is not None else 'null'} | "
            f"{metrics.get('steps', 'null')} | {total_tokens if total_tokens is not None else 'null'} | "
            f"{cost_text} | {estimate_text} | {duration_text} |"
        )
    lines.extend(["", "Results are raw development evidence; no performance numbers are prefilled.", ""])
    return "\n".join(lines)


__all__ = [
    "BenchmarkBudget",
    "BenchmarkConfig",
    "BenchmarkEngine",
    "BenchmarkModel",
    "BenchmarkPreflight",
    "BenchmarkResult",
    "BenchmarkRun",
    "BenchmarkRunner",
    "BenchmarkTask",
    "Engine",
    "EngineExecutor",
    "EngineRequest",
    "EngineRun",
    "canonical_snapshot_sha256",
    "capture_commits",
    "capture_patch",
    "copy_snapshot",
    "initialize_git_snapshot",
    "load_task_manifest",
    "load_tasks",
    "preflight_benchmark_image",
    "run_benchmark",
    "run_hidden_verifier",
]
