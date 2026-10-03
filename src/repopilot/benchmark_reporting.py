"""Benchmark result accounting, redaction and reports, including legacy evidence."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any

from repopilot.environment import docker_proxy_run_args
from repopilot.evaluation import aggregate, markdown
from repopilot.pricing import estimate_openai_standard_cost

if TYPE_CHECKING:
    from repopilot.benchmark import BenchmarkConfig, BenchmarkEngine, BenchmarkRun, EngineRun


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
    from repopilot.benchmark import BenchmarkEngine

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


def _text(value: str | bytes | None) -> str:
    if isinstance(value, bytes):
        return value.decode(errors="replace")
    return value or ""


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
