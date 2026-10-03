"""Explicit baseline and RepoPilot execution adapters, separate from the runner."""

from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from minisweagent.config import builtin_config_dir
from minisweagent.utils.serialize import recursive_merge
from repopilot.approval import ApprovalContext
from repopilot.artifacts import RunArtifacts
from repopilot.benchmark_reporting import (
    _baseline_model_stats,
    _benchmark_secret_values,
    _redact_benchmark_value,
    _trajectory_status,
)
from repopilot.environment import docker_proxy_run_args
from repopilot.evaluation import ScenarioObserver
from repopilot.model import AssistantTurn, LiteLLMToolCallingModel, stream_chunk_record
from repopilot.plan import PlanHistory

if TYPE_CHECKING:
    from repopilot.benchmark import BenchmarkModel, EngineRequest, EngineRun
    from repopilot.runtime import AgentRunResult


def run_baseline(
    request: EngineRequest, *, model_factory, environment_factory, agent_factory, config_factory
) -> EngineRun:
    from repopilot.benchmark import BenchmarkEngine, EngineRun

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
    model = model_factory(config=model_config)
    if model_kwargs.get("stream") and hasattr(model, "_query"):
        stream_number = 0

        def observe_stream(sequence, chunk):
            nonlocal stream_number
            if sequence == 0:
                stream_number += 1
            record = _redact_benchmark_value(stream_chunk_record(sequence, chunk), _benchmark_secret_values(config))
            path = request.artifact_directory / f"model-stream-{stream_number:04d}.jsonl"
            with path.open("a") as stream:
                stream.write(json.dumps(record) + "\n")

        model.stream_observer = observe_stream
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
        environment_factory(environment_config, default_type="docker"), request.workspace, request.task.behavior_spec
    )
    agent_config = recursive_merge(
        config_factory(builtin_config_dir / "mini.yaml").get("agent", {}),
        {
            "step_limit": run_budget.max_steps,
            "wall_time_limit_seconds": max(1, int(run_budget.max_run_seconds)),
            "cost_limit": 0,
            # Upstream saves on every step.  Keep that intermediate serialization
            # in memory so the benchmark seam can redact it before persistence.
            "output_path": None,
        },
    )
    agent = agent_factory(model, environment, agent_config, default_type="default")
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
        evaluation_events=environment.events + [environment.audit()],
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

    def complete(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]], *, timeout_seconds=None
    ) -> AssistantTurn:
        turn = super().complete(messages, tools, timeout_seconds=timeout_seconds)
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


def run_repopilot(
    request: EngineRequest, *, runtime_factory, context_factory, registry_factory, environment_factory
) -> EngineRun:
    from repopilot.benchmark import EngineRun

    config = request.config
    model = _BenchmarkToolCallingModel(model=config.model)
    environment = environment_factory(
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
    runtime = runtime_factory(
        model,
        registry_factory(
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
        context=context_factory(),
        progress_detection_enabled=config.progress_detection_enabled,
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
        evaluation_events=environment.events + [environment.audit()],
        error=_redact_benchmark_value(error, _benchmark_secret_values(config)),
    )


def _copy_runtime_artifacts(source: Path, destination: Path) -> None:
    for path in source.iterdir():
        if path.name == "objects" and path.is_dir():
            shutil.copytree(path, destination / "objects", dirs_exist_ok=True)
            continue
        if path.name == "result.json":
            continue
        name = {"patch.diff": "runtime-patch.diff", "patch-manifest.json": "runtime-patch-manifest.json"}.get(
            path.name, path.name
        )
        target = destination / name
        if path.is_file():
            shutil.copy2(path, target)
            if path.name == "patch-manifest.json":
                manifest = json.loads(target.read_text())
                manifest["patch"] = "runtime-patch.diff"
                manifest["replay"] = "Apply initial-worktree.diff to baseline HEAD, then runtime-patch.diff."
                target.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")


def _cleanup_baseline_environment(environment: Any) -> None:
    cleanup = getattr(environment, "cleanup", None)
    if callable(cleanup):
        cleanup()
    else:
        close = getattr(environment, "close", None)
        if callable(close):
            close()


def _host_identity() -> str:
    try:
        return f"{os.getuid()}:{os.getgid()}"
    except AttributeError:
        return ""
