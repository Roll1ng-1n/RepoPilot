"""A small, pinned SWE-bench Lite smoke seam.

This module intentionally owns only the external smoke workflow.  It loads one
fixed public instance, proves that its local Docker image and the official
evaluator are usable, and only then asks a caller-provided model factory for a
model.  The model and agent are injectable so the preflight path never needs a
provider credential and remains cheap to test.
"""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from repopilot.approval import ApprovalContext
from repopilot.artifacts import RunArtifacts
from repopilot.budget import BudgetExceeded, RunBudget
from repopilot.context import ContextManager
from repopilot.environment import Command, CommandResult, ExecutionEnvironment
from repopilot.plan import PlanHistory
from repopilot.runtime import AgentRuntime
from repopilot.tools import create_tool_registry

DATASET_NAME = "SWE-bench/SWE-bench_Lite"
DATASET_REVISION = "b0dde1093fe417d83b7184254edf8199c1f0dff5"
SPLIT = "dev"
INSTANCE_ID = "sqlfluff__sqlfluff-1625"
DEFAULT_IMAGE = "docker.io/swebench/sweb.eval.x86_64.sqlfluff_1776_sqlfluff-1625:latest"


class DatasetLoader(Protocol):
    def __call__(self, path: str, **kwargs: Any) -> Sequence[Mapping[str, Any]]: ...


class CommandRunner(Protocol):
    def __call__(self, argv: list[str], timeout: float) -> subprocess.CompletedProcess[str]: ...


ModelFactory = Callable[[dict[str, Any]], Any]


@dataclass(frozen=True)
class SWEbenchSmokeConfig:
    """Bounded settings for the one-instance external smoke.

    Dataset identity and instance selection are constants above on purpose.  A
    caller may change the output location, model, image tag used by a local
    test, and resource limits, but cannot accidentally turn this smoke into an
    unpinned benchmark invocation.
    """

    output_directory: Path
    model_name: str = "unspecified"
    model_kwargs: Mapping[str, Any] = field(default_factory=dict)
    image: str = DEFAULT_IMAGE
    max_steps: int = 50
    max_replans: int = 2
    max_consecutive_failures: int = 3
    command_timeout_seconds: float = 300.0
    max_run_seconds: float = 30.0 * 60.0
    max_cost_usd: float = 3.0
    max_workers: int = 1
    verifier_timeout_seconds: float = 1_800.0
    docker_executable: str = field(default_factory=lambda: os.getenv("MSWEA_DOCKER_EXECUTABLE", "docker"))

    def __post_init__(self) -> None:
        if not self.image.strip():
            raise ValueError("SWE-bench smoke requires a Docker image.")
        if self.max_steps < 1:
            raise ValueError("max_steps must be at least 1.")
        if self.max_replans < 0:
            raise ValueError("max_replans must not be negative.")
        if self.max_consecutive_failures < 1:
            raise ValueError("max_consecutive_failures must be at least 1.")
        if self.command_timeout_seconds <= 0 or self.max_run_seconds <= 0:
            raise ValueError("SWE-bench smoke time limits must be positive.")
        if self.max_cost_usd < 0:
            raise ValueError("max_cost_usd must not be negative.")
        if self.max_workers != 1:
            raise ValueError("SWE-bench smoke uses max_workers=1.")
        if self.verifier_timeout_seconds <= 0:
            raise ValueError("verifier_timeout_seconds must be positive.")

    @property
    def instance_id(self) -> str:
        return INSTANCE_ID

    @property
    def dataset_name(self) -> str:
        return DATASET_NAME

    @property
    def dataset_revision(self) -> str:
        return DATASET_REVISION

    @property
    def split(self) -> str:
        return SPLIT

    def public_dict(self) -> dict[str, Any]:
        return {
            "dataset_name": DATASET_NAME,
            "dataset_revision": DATASET_REVISION,
            "split": SPLIT,
            "instance_ids": [INSTANCE_ID],
            "image": self.image,
            "model_name": self.model_name,
            "model_kwargs": dict(self.model_kwargs),
            "max_steps": self.max_steps,
            "max_replans": self.max_replans,
            "max_consecutive_failures": self.max_consecutive_failures,
            "command_timeout_seconds": self.command_timeout_seconds,
            "max_run_seconds": self.max_run_seconds,
            "max_cost_usd": self.max_cost_usd,
            "max_workers": self.max_workers,
            "verifier_timeout_seconds": self.verifier_timeout_seconds,
        }


@dataclass(frozen=True)
class AgentExecution:
    """Portable terminal output from a RepoPilot agent execution."""

    status: str
    patch: str = ""
    trajectory: Any = None
    model_calls: int = 0
    cost_usd: float | None = None
    error: str | None = None


AgentRunner = Callable[[dict[str, Any], Any, Path, SWEbenchSmokeConfig], AgentExecution]


@dataclass(frozen=True)
class PreflightResult:
    """Evidence from the no-model Docker and official-verifier checks."""

    status: str
    image: str
    checks: tuple[dict[str, Any], ...]
    error: str | None = None

    @property
    def ready(self) -> bool:
        return self.status == "READY"

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "image": self.image,
            "checks": list(self.checks),
            "error": self.error,
        }


@dataclass(frozen=True)
class SWEbenchSmokeResult:
    """Persisted outcome for the fixed smoke instance."""

    instance_id: str
    status: str
    success: bool | None
    artifact_directory: Path
    metrics: dict[str, Any]
    preflight: dict[str, Any]
    verifier: dict[str, Any] | None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "instance_id": self.instance_id,
            "status": self.status,
            "success": self.success,
            "artifact_directory": str(self.artifact_directory),
            "metrics": self.metrics,
            "preflight": self.preflight,
            "verifier": self.verifier,
            "error": self.error,
        }


def load_pinned_instance(*, loader: DatasetLoader | None = None) -> dict[str, Any]:
    """Load the one canonical row from the pinned dataset revision."""

    if loader is None:
        from datasets import load_dataset  # type: ignore[import-untyped]

        loader = load_dataset
    rows = loader(DATASET_NAME, revision=DATASET_REVISION, split=SPLIT)
    for row in rows:
        if row.get("instance_id") == INSTANCE_ID:
            return dict(row)
    raise ValueError(f"Pinned SWE-bench instance was not found: {INSTANCE_ID}")


def preflight_swebench(
    config: SWEbenchSmokeConfig,
    *,
    artifact_directory: Path,
    command_runner: CommandRunner | None = None,
    loader: DatasetLoader | None = None,
) -> PreflightResult:
    """Check a local image, start it once, and run the official gold verifier.

    Every command uses ``--pull=never`` where Docker is involved.  Therefore a
    missing local image is a quick, explicit environment failure and cannot
    trigger an implicit network pull or a model call.  The pinned dataset row
    is loaded only after those Docker checks pass and is then used by the
    verifier as a local JSON dataset.
    """

    run_command = command_runner or _run_command
    checks: list[dict[str, Any]] = []
    docker = config.docker_executable
    inspect_command = [docker, "image", "inspect", config.image]
    inspected, inspect_error = _invoke_check(run_command, inspect_command, config.command_timeout_seconds)
    checks.append(inspected)
    if inspect_error is not None or inspected["exit_code"] != 0:
        detail = inspect_error or inspected.get("stderr") or "Docker image is not available locally."
        return PreflightResult("ENVIRONMENT_UNAVAILABLE", config.image, tuple(checks), str(detail))

    container_command = [
        docker,
        "run",
        "--rm",
        "--pull=never",
        config.image,
        "bash",
        "-lc",
        "test -d /testbed",
    ]
    started, start_error = _invoke_check(run_command, container_command, config.command_timeout_seconds)
    checks.append(started)
    if start_error is not None or started["exit_code"] != 0:
        detail = start_error or started.get("stderr") or "SWE-bench Docker environment could not start."
        return PreflightResult("ENVIRONMENT_UNAVAILABLE", config.image, tuple(checks), str(detail))

    try:
        instance = load_pinned_instance(loader=loader)
        dataset_path = artifact_directory / "dataset.json"
        dataset_path.write_text(
            json.dumps([instance], indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except Exception as exception:
        detail = str(exception) or type(exception).__name__
        return PreflightResult("DATASET_UNAVAILABLE", config.image, tuple(checks), detail)

    report_directory = artifact_directory / "preflight-report"
    _reset_report_directory(report_directory)
    verifier_command = _official_verifier_command(
        config,
        predictions_path="gold",
        report_directory=report_directory,
        run_id="repopilot-swebench-smoke-preflight",
        dataset_name=str(dataset_path),
    )
    verified, verifier_error = _invoke_check(run_command, verifier_command, config.verifier_timeout_seconds)
    report_error = _attach_official_report(verified, report_directory)
    checks.append(verified)
    (artifact_directory / "preflight-test-output.txt").write_text(
        f"stdout:\n{verified.get('stdout', '')}\nstderr:\n{verified.get('stderr', '')}\n",
        encoding="utf-8",
    )
    if verifier_error is not None or verified["exit_code"] != 0 or report_error is not None:
        detail = (
            verifier_error
            or report_error
            or verified.get("stderr")
            or "The official SWE-bench verifier preflight failed."
        )
        return PreflightResult("VERIFIER_UNAVAILABLE", config.image, tuple(checks), str(detail))
    if INSTANCE_ID not in verified["resolved_ids"]:
        return PreflightResult(
            "VERIFIER_UNAVAILABLE",
            config.image,
            tuple(checks),
            f"The official SWE-bench verifier did not resolve {INSTANCE_ID} during preflight.",
        )
    return PreflightResult("READY", config.image, tuple(checks))


def run_swebench_smoke(
    config: SWEbenchSmokeConfig,
    *,
    model_factory: ModelFactory | None = None,
    agent_runner: AgentRunner | None = None,
    loader: DatasetLoader | None = None,
    dataset_loader: DatasetLoader | None = None,
    command_runner: CommandRunner | None = None,
) -> SWEbenchSmokeResult:
    """Run the pinned one-instance smoke and persist auditable artifacts.

    ``model_factory`` is called exactly once, and only after all preflight
    checks pass.  A caller can provide ``agent_runner`` to adapt an existing
    engine; absent one, the default uses RepoPilot's native Tool Calling
    runtime against the upstream mini-SWE-agent Docker lifecycle.
    """

    if loader is not None and dataset_loader is not None:
        raise ValueError("Pass only one of loader or dataset_loader.")
    config.output_directory.mkdir(parents=True, exist_ok=True)
    artifact_directory = config.output_directory / INSTANCE_ID
    artifact_directory.mkdir(parents=True, exist_ok=True)
    for filename in ("patch.diff", "preds.json", "trajectory.json", "verifier.json", "result.json"):
        (artifact_directory / filename).unlink(missing_ok=True)
    (artifact_directory / "config.json").write_text(
        json.dumps(config.public_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    artifacts = RunArtifacts(artifact_directory / "run-state", secrets=[])
    artifacts.append_trace(
        "run_started",
        dataset_name=DATASET_NAME,
        dataset_revision=DATASET_REVISION,
        split=SPLIT,
        instance_id=INSTANCE_ID,
        image=config.image,
        model=config.model_name,
    )

    preflight = preflight_swebench(
        config,
        artifact_directory=artifact_directory,
        command_runner=command_runner,
        loader=loader or dataset_loader,
    )
    artifacts.append_trace("preflight_finished", **preflight.to_dict())
    (artifact_directory / "preflight.json").write_text(
        json.dumps(preflight.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    if not preflight.ready:
        return _finish_result(
            config=config,
            artifact_directory=artifact_directory,
            artifacts=artifacts,
            preflight=preflight,
            status=preflight.status,
            success=None,
            metrics={"model_calls": 0, "cost_usd": None},
            verifier=None,
            error=preflight.error,
        )

    try:
        instance = _read_materialized_instance(artifact_directory / "dataset.json")
    except Exception as exception:
        return _finish_result(
            config=config,
            artifact_directory=artifact_directory,
            artifacts=artifacts,
            preflight=preflight,
            status="DATASET_UNAVAILABLE",
            success=None,
            metrics={"model_calls": 0, "cost_usd": None},
            verifier=None,
            error=str(exception) or type(exception).__name__,
        )

    if model_factory is None:
        return _finish_result(
            config=config,
            artifact_directory=artifact_directory,
            artifacts=artifacts,
            preflight=preflight,
            status="MODEL_UNAVAILABLE",
            success=None,
            metrics={"model_calls": 0, "cost_usd": None},
            verifier=None,
            error="No model factory was provided after successful preflight.",
        )

    try:
        model = model_factory(instance)
    except Exception as exception:
        return _finish_result(
            config=config,
            artifact_directory=artifact_directory,
            artifacts=artifacts,
            preflight=preflight,
            status="MODEL_UNAVAILABLE",
            success=None,
            metrics={"model_calls": 0, "cost_usd": None},
            verifier=None,
            error=str(exception) or type(exception).__name__,
        )

    execute_agent: AgentRunner
    if agent_runner is None:

        def execute_default_agent(
            current_instance: dict[str, Any],
            current_model: Any,
            current_directory: Path,
            current_config: SWEbenchSmokeConfig,
        ) -> AgentExecution:
            return _run_repopilot_agent(
                current_instance,
                current_model,
                current_directory,
                current_config,
                artifacts=artifacts,
            )

        execute_agent = execute_default_agent
    else:
        execute_agent = agent_runner
    started_at = time.monotonic()
    try:
        execution = execute_agent(instance, model, artifact_directory, config)
    except Exception as exception:
        execution = AgentExecution(
            status="MODEL_FAILED",
            model_calls=_model_calls(model),
            cost_usd=_model_cost(model),
            error=str(exception) or type(exception).__name__,
        )
    duration = time.monotonic() - started_at
    patch = execution.patch if isinstance(execution.patch, str) else ""
    (artifact_directory / "patch.diff").write_text(patch, encoding="utf-8")
    if execution.trajectory is not None:
        (artifact_directory / "trajectory.json").write_text(
            json.dumps(execution.trajectory, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8"
        )
    predictions_path = artifact_directory / "preds.json"
    predictions_path.write_text(
        json.dumps(
            {
                INSTANCE_ID: {
                    "model_name_or_path": config.model_name,
                    "instance_id": INSTANCE_ID,
                    "model_patch": patch,
                }
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    metrics = {
        "model_calls": execution.model_calls or _model_calls(model),
        "cost_usd": execution.cost_usd if execution.cost_usd is not None else _model_cost(model),
        "duration_seconds": duration,
        "max_steps": config.max_steps,
        "max_cost_usd": config.max_cost_usd,
    }
    if metrics["cost_usd"] is not None and metrics["cost_usd"] > config.max_cost_usd:
        return _finish_result(
            config=config,
            artifact_directory=artifact_directory,
            artifacts=artifacts,
            preflight=preflight,
            status="BUDGET_EXCEEDED",
            success=None,
            metrics=metrics,
            verifier=None,
            error=f"Model cost exceeded the smoke limit of ${config.max_cost_usd:.2f}.",
        )
    if execution.status not in {"SUCCEEDED", "Submitted"}:
        return _finish_result(
            config=config,
            artifact_directory=artifact_directory,
            artifacts=artifacts,
            preflight=preflight,
            status=execution.status,
            success=None,
            metrics=metrics,
            verifier=None,
            error=execution.error,
        )

    report_directory = artifact_directory / "verifier-report"
    _reset_report_directory(report_directory)
    verifier = run_official_verifier(
        config,
        predictions_path=predictions_path,
        report_directory=report_directory,
        command_runner=command_runner,
        dataset_name=str(artifact_directory / "dataset.json"),
    )
    success = verifier.get("exit_code") == 0 and INSTANCE_ID in verifier.get("resolved_ids", [])
    status = execution.status if success else "FAILED_VERIFICATION"
    return _finish_result(
        config=config,
        artifact_directory=artifact_directory,
        artifacts=artifacts,
        preflight=preflight,
        status=status,
        success=success,
        metrics=metrics,
        verifier=verifier,
        error=execution.error,
    )


def run_official_verifier(
    config: SWEbenchSmokeConfig,
    *,
    predictions_path: Path,
    report_directory: Path,
    command_runner: CommandRunner | None = None,
    dataset_name: str = DATASET_NAME,
) -> dict[str, Any]:
    """Run the official SWE-bench evaluator on a model prediction file."""

    _reset_report_directory(report_directory)
    command = _official_verifier_command(
        config,
        predictions_path=str(predictions_path),
        report_directory=report_directory,
        run_id="repopilot-swebench-smoke",
        dataset_name=dataset_name,
    )
    result, error = _invoke_check(
        command_runner or _run_command,
        command,
        config.verifier_timeout_seconds,
    )
    (report_directory / "test_output.txt").write_text(
        f"stdout:\n{result.get('stdout', '')}\nstderr:\n{result.get('stderr', '')}\n",
        encoding="utf-8",
    )
    report_error = _attach_official_report(result, report_directory)
    if error is not None:
        result["error"] = error
    elif report_error is not None:
        result["error"] = report_error
    result["command"] = command
    result["report_directory"] = str(report_directory)
    return result


def _official_verifier_command(
    config: SWEbenchSmokeConfig,
    *,
    predictions_path: str,
    report_directory: Path,
    run_id: str,
    dataset_name: str = DATASET_NAME,
) -> list[str]:
    return [
        sys.executable,
        "-m",
        "swebench.harness.run_evaluation",
        "--dataset_name",
        dataset_name,
        "--split",
        SPLIT,
        "--instance_ids",
        INSTANCE_ID,
        "--predictions_path",
        predictions_path,
        "--max_workers",
        str(config.max_workers),
        "--run_id",
        run_id,
        "--timeout",
        str(int(config.verifier_timeout_seconds)),
        "--report_dir",
        str(report_directory),
    ]


def _reset_report_directory(report_directory: Path) -> None:
    report_directory.mkdir(parents=True, exist_ok=True)
    for report_path in report_directory.glob("*.json"):
        report_path.unlink()


def _attach_official_report(result: dict[str, Any], report_directory: Path) -> str | None:
    report, error = _read_official_report(report_directory)
    if error is not None:
        result["report_error"] = error
        return error
    assert report is not None
    resolved_ids = report.get("resolved_ids")
    assert isinstance(resolved_ids, list)
    result["resolved_ids"] = resolved_ids
    result["resolved"] = INSTANCE_ID in resolved_ids
    result["report"] = report
    result["report_path"] = str(report["_path"])
    del report["_path"]
    return None


def _read_official_report(report_directory: Path) -> tuple[dict[str, Any] | None, str | None]:
    report_paths = sorted(report_directory.glob("*.json"), key=lambda path: path.stat().st_mtime_ns, reverse=True)
    if not report_paths:
        return None, "The official SWE-bench verifier did not produce a report JSON."

    errors: list[str] = []
    for report_path in report_paths:
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exception:
            errors.append(f"{report_path.name}: {exception}")
            continue
        if not isinstance(report, dict) or not isinstance(report.get("resolved_ids"), list):
            errors.append(f"{report_path.name}: missing a resolved_ids list")
            continue
        report["_path"] = report_path
        return report, None

    detail = "; ".join(errors)
    return None, f"The official SWE-bench report JSON was invalid{': ' + detail if detail else '.'}"


def _read_materialized_instance(dataset_path: Path) -> dict[str, Any]:
    rows = json.loads(dataset_path.read_text(encoding="utf-8"))
    if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict):
        raise ValueError("Materialized SWE-bench dataset must contain exactly one instance row.")
    instance = rows[0]
    if instance.get("instance_id") != INSTANCE_ID:
        raise ValueError(f"Materialized SWE-bench instance was not {INSTANCE_ID}.")
    return instance


def _invoke_check(
    command_runner: CommandRunner,
    command: list[str],
    timeout: float,
) -> tuple[dict[str, Any], str | None]:
    started_at = time.monotonic()
    try:
        completed = command_runner(command, timeout)
        return (
            {
                "command": command,
                "exit_code": completed.returncode,
                "stdout": completed.stdout or "",
                "stderr": completed.stderr or "",
                "duration_seconds": time.monotonic() - started_at,
            },
            None,
        )
    except subprocess.TimeoutExpired as exception:
        return (
            {
                "command": command,
                "exit_code": -1,
                "stdout": _text(exception.stdout),
                "stderr": _text(exception.stderr) or f"Command timed out after {timeout} seconds.",
                "duration_seconds": time.monotonic() - started_at,
                "timed_out": True,
            },
            str(exception),
        )
    except OSError as exception:
        return (
            {
                "command": command,
                "exit_code": -1,
                "stdout": "",
                "stderr": str(exception),
                "duration_seconds": time.monotonic() - started_at,
            },
            str(exception),
        )


def _run_command(argv: list[str], timeout: float) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, capture_output=True, text=True, check=False, timeout=timeout)


def _finish_result(
    *,
    config: SWEbenchSmokeConfig,
    artifact_directory: Path,
    artifacts: RunArtifacts,
    preflight: PreflightResult,
    status: str,
    success: bool | None,
    metrics: dict[str, Any],
    verifier: dict[str, Any] | None,
    error: str | None,
) -> SWEbenchSmokeResult:
    if not (artifact_directory / "patch.diff").is_file():
        (artifact_directory / "patch.diff").write_text("", encoding="utf-8")
    if verifier is not None:
        (artifact_directory / "verifier.json").write_text(
            json.dumps(verifier, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8"
        )
    artifacts.append_trace(
        "run_finished",
        status=status,
        success=success,
        model_calls=metrics.get("model_calls", 0),
        cost_usd=metrics.get("cost_usd"),
        error=error,
    )
    artifacts.write_metadata(
        {
            "status": status,
            "success": success,
            "instance_id": INSTANCE_ID,
            "dataset_name": DATASET_NAME,
            "dataset_revision": DATASET_REVISION,
            "split": SPLIT,
            "image": config.image,
            "model": config.model_name,
            "metrics": metrics,
            "preflight": preflight.to_dict(),
            "verifier": verifier,
            "error": error,
        }
    )
    _publish_artifacts(artifacts.path, artifact_directory)
    result = SWEbenchSmokeResult(
        instance_id=INSTANCE_ID,
        status=status,
        success=success,
        artifact_directory=artifact_directory,
        metrics=metrics,
        preflight=preflight.to_dict(),
        verifier=verifier,
        error=error,
    )
    (artifact_directory / "result.json").write_text(
        json.dumps(result.to_dict(), indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8"
    )
    return result


def _publish_artifacts(source: Path, destination: Path) -> None:
    for filename in (
        "metadata.json",
        "trace.jsonl",
        "checkpoint.json",
        "plan.json",
        "verification.json",
        "task_report.md",
    ):
        source_file = source / filename
        if source_file.is_file():
            shutil.copy2(source_file, destination / filename)


def _model_calls(model: Any) -> int:
    value = getattr(model, "calls", getattr(model, "n_calls", 0))
    return value if isinstance(value, int) else 0


def _model_cost(model: Any) -> float | None:
    value = getattr(model, "cost", None)
    return float(value) if isinstance(value, (float, int)) and not isinstance(value, bool) else None


def _trace_model_calls(artifacts: RunArtifacts) -> int:
    return sum(1 for event in artifacts.read_trace() if event.get("type") == "model_response")


def _trace_model_cost(artifacts: RunArtifacts) -> float | None:
    costs = [
        float(event["cost_usd"])
        for event in artifacts.read_trace()
        if event.get("type") == "model_response"
        and isinstance(event.get("cost_usd"), (int, float))
        and not isinstance(event.get("cost_usd"), bool)
    ]
    return sum(costs) if costs else None


def _text(value: str | bytes | None) -> str:
    if isinstance(value, bytes):
        return value.decode(errors="replace")
    return value or ""


class _MiniEnvironmentAdapter:
    """Adapt mini-SWE-agent's shell environment to RepoPilot's Command port."""

    def __init__(self, environment: Any, *, maximum_timeout: float):
        self._environment = environment
        self._maximum_timeout = maximum_timeout

    def execute(self, command: Command) -> CommandResult:
        started_at = time.monotonic()
        shell_command = shlex.join(command.argv)
        if command.stdin is not None:
            shell_command = f"printf %s {shlex.quote(command.stdin)} | {shell_command}"
        output = self._environment.execute(
            {"command": shell_command},
            timeout=max(1, int(min(command.timeout_seconds, self._maximum_timeout))),
        )
        return CommandResult(
            exit_code=int(output.get("returncode", -1)),
            stdout=str(output.get("output", "")),
            stderr=str(output.get("exception_info", "")),
            duration_seconds=time.monotonic() - started_at,
            truncated=False,
        )

    def close(self) -> None:
        cleanup = getattr(self._environment, "cleanup", None)
        if callable(cleanup):
            cleanup()


class _CostLimitedModel:
    """Track and bound provider cost while retaining the native model seam."""

    def __init__(self, model: Any, limit: float):
        self._model = model
        self._limit = limit
        self.model_name = str(getattr(model, "model_name", "model"))
        self.calls = 0
        self.cost: float | None = 0.0

    def complete(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> Any:
        if self.cost is not None and self.cost >= self._limit:
            raise BudgetExceeded("cost_usd")
        turn = self._model.complete(messages, tools)
        self.calls += 1
        value = getattr(turn, "cost", None)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            self.cost = (self.cost or 0.0) + float(value)
        else:
            self.cost = None
        return turn


def _run_repopilot_agent(
    instance: dict[str, Any],
    model: Any,
    artifact_directory: Path,
    config: SWEbenchSmokeConfig,
    *,
    artifacts: RunArtifacts | None = None,
) -> AgentExecution:
    """Run RepoPilot's native runtime in the preflighted SWE-bench container."""

    from minisweagent.environments import get_environment

    plan_history = PlanHistory.for_task(str(instance.get("problem_statement", "")))
    budget = RunBudget(
        max_steps=config.max_steps,
        max_replans=config.max_replans,
        max_consecutive_failures=config.max_consecutive_failures,
        command_timeout_seconds=config.command_timeout_seconds,
        max_run_seconds=config.max_run_seconds,
    )
    runtime_artifacts = artifacts or RunArtifacts(artifact_directory / "agent-state", secrets=[])
    limited_model = _CostLimitedModel(model, config.max_cost_usd)
    adapter: ExecutionEnvironment | None = None
    try:
        try:
            environment = get_environment(
                {
                    "environment_class": "docker",
                    "image": config.image,
                    "cwd": "/testbed",
                    "timeout": max(1, int(config.command_timeout_seconds)),
                    "run_args": ["--rm", "--pull=never"],
                }
            )
        except Exception as exception:
            return AgentExecution(
                status="ENVIRONMENT_UNAVAILABLE",
                error=str(exception) or type(exception).__name__,
            )
        adapter = _MiniEnvironmentAdapter(
            environment,
            maximum_timeout=config.command_timeout_seconds,
        )
        runtime = AgentRuntime(
            limited_model,
            create_tool_registry(
                adapter,
                artifact_directory,
                plan_history,
                command_timeout_seconds=config.command_timeout_seconds,
            ),
            runtime_artifacts,
            plan_history,
            budget,
            context=ContextManager(),
            approval_context=ApprovalContext(
                environment="docker",
                disposable_benchmark=True,
                automatic_approval=True,
            ),
        )
        result = runtime.run(str(instance.get("problem_statement", "")), artifact_directory)
        patch_path = runtime_artifacts.path / "patch.diff"
        patch = patch_path.read_text(encoding="utf-8") if patch_path.is_file() else ""
        return AgentExecution(
            status=result.status,
            patch=patch,
            trajectory={"run_id": result.run_id, "status": result.status, "plan": result.plan.to_dict()},
            model_calls=limited_model.calls or _trace_model_calls(runtime_artifacts),
            cost_usd=limited_model.cost if limited_model.cost is not None else _trace_model_cost(runtime_artifacts),
        )
    except BudgetExceeded as exception:
        return AgentExecution(
            status="BUDGET_EXCEEDED",
            model_calls=limited_model.calls or _trace_model_calls(runtime_artifacts),
            cost_usd=limited_model.cost if limited_model.cost is not None else _trace_model_cost(runtime_artifacts),
            error=str(exception),
        )
    finally:
        if adapter is not None:
            adapter.close()
