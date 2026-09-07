"""Sequential multi-model, multi-round benchmark campaigns.

This module is intentionally a thin wrapper around :mod:`repopilot.benchmark`.
The benchmark runner remains responsible for one paired baseline/RepoPilot run;
the campaign only chooses the model and output directory for each round and
combines the resulting records into one report.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from repopilot.benchmark import (
    DEFAULT_BENCHMARK_IMAGE,
    BenchmarkBudget,
    BenchmarkConfig,
    BenchmarkEngine,
    BenchmarkModel,
    BenchmarkResult,
    BenchmarkRun,
    EngineExecutor,
    _coerce_engine,
    run_benchmark,
)
from repopilot.environment import DockerProxyMode
from repopilot.evaluation import aggregate, markdown
from repopilot.pricing import OPENAI_STANDARD_PRICING_AS_OF, OPENAI_STANDARD_PRICING_SOURCE

BenchmarkRunnerCallable = Callable[[BenchmarkConfig], BenchmarkRun]


@dataclass(frozen=True, init=False)
class CampaignConfig:
    """Configuration shared by every paired run in a campaign.

    ``output_directory``/``tasks_directory`` are the canonical names used by
    ``BenchmarkConfig``.  ``output_root``/``tasks_dir`` are accepted as
    convenient aliases because a campaign is commonly configured from a CLI or
    a small experiment script.
    """

    output_directory: Path
    tasks_directory: Path
    models: tuple[str, ...]
    rounds: int
    image: str
    budget: BenchmarkBudget
    engines: tuple[BenchmarkEngine, ...]
    task_ids: tuple[str, ...]
    temperature: float
    stream: bool
    api_key: str | None = field(repr=False)
    base_url: str | None = field(repr=False)
    proxy_mode: DockerProxyMode
    proxy_url: str | None = field(repr=False)

    def __init__(
        self,
        output_directory: Path | None = None,
        tasks_directory: Path | None = None,
        models: Sequence[str] | str = (),
        *,
        output_root: Path | None = None,
        tasks_dir: Path | None = None,
        rounds: int = 1,
        repeats: int | None = None,
        image: str = DEFAULT_BENCHMARK_IMAGE,
        budget: BenchmarkBudget | None = None,
        engines: Sequence[BenchmarkEngine | str] = (
            BenchmarkEngine.BASELINE,
            BenchmarkEngine.REPOPILOT,
        ),
        task_ids: Sequence[str] = (),
        temperature: float = 0.0,
        api_key: str | None = None,
        base_url: str | None = None,
        stream: bool = False,
        proxy_mode: DockerProxyMode | str | None = None,
        proxy_url: str | None = None,
        proxy: DockerProxyMode | str | Mapping[str, Any] | None = None,
    ) -> None:
        if repeats is not None:
            if rounds != 1 and rounds != repeats:
                raise ValueError("rounds and repeats disagree")
            rounds = repeats
        resolved_output = output_directory if output_directory is not None else output_root
        resolved_tasks = tasks_directory if tasks_directory is not None else tasks_dir
        if resolved_output is None:
            raise TypeError("CampaignConfig requires output_directory (or output_root).")
        if resolved_tasks is None:
            raise TypeError("CampaignConfig requires tasks_directory (or tasks_dir).")

        if isinstance(models, str):
            normalized_models = (models,)
        else:
            normalized_models = tuple(models)
        if not normalized_models or any(not isinstance(model, str) or not model.strip() for model in normalized_models):
            raise ValueError("CampaignConfig requires at least one non-empty model ID.")
        if isinstance(rounds, bool) or not isinstance(rounds, int) or rounds < 1:
            raise ValueError("rounds must be a positive integer.")
        if isinstance(temperature, bool) or not isinstance(temperature, (int, float)):
            raise ValueError("temperature must be numeric.")
        if not isinstance(stream, bool):
            raise ValueError("stream must be a bool.")

        if isinstance(engines, (str, BenchmarkEngine)):
            engines = (engines,)
        normalized_engines = tuple(_coerce_engine(engine) for engine in engines)
        normalized_engines = tuple(dict.fromkeys(normalized_engines))
        if not normalized_engines:
            raise ValueError("CampaignConfig requires at least one benchmark engine.")

        mode, url = _normalize_proxy(proxy_mode, proxy_url, proxy)
        object.__setattr__(self, "output_directory", Path(resolved_output))
        object.__setattr__(self, "tasks_directory", Path(resolved_tasks))
        object.__setattr__(self, "models", normalized_models)
        object.__setattr__(self, "rounds", rounds)
        object.__setattr__(self, "image", image)
        object.__setattr__(self, "budget", budget or BenchmarkBudget())
        object.__setattr__(self, "engines", normalized_engines)
        object.__setattr__(self, "task_ids", (task_ids,) if isinstance(task_ids, str) else tuple(task_ids))
        object.__setattr__(self, "temperature", float(temperature))
        object.__setattr__(self, "stream", bool(stream))
        object.__setattr__(self, "api_key", api_key)
        object.__setattr__(self, "base_url", base_url)
        object.__setattr__(self, "proxy_mode", mode)
        object.__setattr__(self, "proxy_url", url)

    @property
    def output_root(self) -> Path:
        """Alias for the root under which model/round directories are made."""

        return self.output_directory

    @property
    def tasks_dir(self) -> Path:
        """Alias for the directory containing benchmark task manifests."""

        return self.tasks_directory

    @property
    def proxy(self) -> str:
        """Return the configured proxy mode, without exposing a proxy URL."""

        return self.proxy_mode.value

    def public_dict(self) -> dict[str, Any]:
        """Return safe campaign configuration for JSON reports.

        API credentials, the endpoint URL, and an explicit proxy URL are
        intentionally omitted.  A campaign summary should be portable and
        safe to publish as development evidence.
        """

        return {
            "output_directory": str(self.output_directory),
            "tasks_directory": str(self.tasks_directory),
            "models": list(self.models),
            "rounds": self.rounds,
            "repeats": self.rounds,
            "image": self.image,
            "budget": asdict(self.budget),
            "engines": [engine.value for engine in self.engines],
            "task_ids": list(self.task_ids),
            "temperature": self.temperature,
            "stream": self.stream,
            "proxy_mode": self.proxy_mode.value,
        }


@dataclass(frozen=True)
class CampaignRun:
    """Combined output of all benchmark results in one campaign."""

    config: CampaignConfig
    results: tuple[dict[str, Any], ...]
    output_directory: Path
    errors: tuple[dict[str, Any], ...] = ()
    benchmark_runs: tuple[BenchmarkRun, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "config": self.config.public_dict(),
            "pricing_basis": {
                "tier": "standard",
                "as_of": OPENAI_STANDARD_PRICING_AS_OF,
                "source": OPENAI_STANDARD_PRICING_SOURCE,
                "note": "Estimate only; not intermediary invoice data.",
            },
            "results": [_without_credentials(result, self.config) for result in self.results],
            "evaluation_summary": aggregate(list(self.results)),
            "errors": [_without_credentials(error, self.config) for error in self.errors],
        }


class CampaignRunner:
    """Run each model/round sequentially using the paired benchmark runner."""

    def __init__(
        self,
        config: CampaignConfig,
        *,
        runner: BenchmarkRunnerCallable | None = None,
        benchmark_runner: BenchmarkRunnerCallable | None = None,
        executors: Mapping[BenchmarkEngine | str, EngineExecutor] | None = None,
    ) -> None:
        if runner is not None and benchmark_runner is not None:
            raise ValueError("Pass only one of runner and benchmark_runner.")
        self.config = config
        self._runner = runner or benchmark_runner
        self._executors = executors

    def run(self) -> CampaignRun:
        root = self.config.output_directory.resolve()
        if (root / "config.json").exists():
            raise FileExistsError(f"Refusing to overwrite campaign configuration: {root}")
        root.mkdir(parents=True, exist_ok=True)
        _write_json(root / "config.json", self.config.public_dict())

        results: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        benchmark_runs: list[BenchmarkRun] = []
        used_slugs: set[str] = set()

        for model in self.config.models:
            slug = _model_slug(model, used_slugs)
            used_slugs.add(slug)
            for round_number in range(1, self.config.rounds + 1):
                round_directory = root / slug / f"round-{round_number:03d}"
                round_directory.mkdir(parents=True, exist_ok=True)
                benchmark_config = self._benchmark_config(model, round_directory)
                try:
                    benchmark_run = self._run_benchmark(benchmark_config)
                except Exception as exception:  # one failed batch must not hide later models
                    error = _without_credentials(_failure_record(model, round_number, exception), self.config)
                    errors.append(error)
                    results.append(error)
                    _write_json(round_directory / "error.json", error)
                    continue
                finally:
                    # A runner may persist partial artifacts before raising;
                    # scrub those just as we scrub a completed run.
                    _scrub_tree(round_directory, self.config)

                benchmark_runs.append(benchmark_run)
                for benchmark_result in benchmark_run.results:
                    merged = _merge_result(model, round_number, benchmark_result, self.config)
                    results.append(merged)

        campaign = CampaignRun(self.config, tuple(results), root, tuple(errors), tuple(benchmark_runs))
        _write_json(root / "summary.json", campaign.to_dict())
        (root / "summary.md").write_text(_summary_markdown(campaign), encoding="utf-8")
        return campaign

    def _run_benchmark(self, config: BenchmarkConfig) -> BenchmarkRun:
        if self._runner is not None:
            return self._runner(config)
        return run_benchmark(config, executors=self._executors)

    def _benchmark_config(self, model: str, output_directory: Path) -> BenchmarkConfig:
        model_kwargs: dict[str, Any] = {"temperature": self.config.temperature}
        if self.config.stream:
            model_kwargs["stream"] = True
        return BenchmarkConfig(
            tasks_directory=self.config.tasks_directory,
            output_directory=output_directory,
            model=BenchmarkModel(
                model_name=_internal_model_name(model),
                model_kwargs=model_kwargs,
                api_key=self.config.api_key,
                base_url=self.config.base_url,
            ),
            image=self.config.image,
            budget=self.config.budget,
            engines=self.config.engines,
            task_ids=self.config.task_ids,
            proxy_mode=self.config.proxy_mode,
            proxy_url=self.config.proxy_url,
        )


def run_campaign(
    config: CampaignConfig,
    *,
    runner: BenchmarkRunnerCallable | None = None,
    benchmark_runner: BenchmarkRunnerCallable | None = None,
    executors: Mapping[BenchmarkEngine | str, EngineExecutor] | None = None,
) -> CampaignRun:
    """Convenience entry point for a sequential multi-model campaign."""

    return CampaignRunner(
        config,
        runner=runner,
        benchmark_runner=benchmark_runner,
        executors=executors,
    ).run()


def _normalize_proxy(
    proxy_mode: DockerProxyMode | str | None,
    proxy_url: str | None,
    proxy: DockerProxyMode | str | Mapping[str, Any] | None,
) -> tuple[DockerProxyMode, str | None]:
    if proxy is not None:
        if proxy_mode is not None or proxy_url is not None:
            raise ValueError("Use proxy or proxy_mode/proxy_url, not both.")
        if isinstance(proxy, Mapping):
            proxy_mode = proxy.get("mode", proxy.get("proxy_mode"))
            proxy_url = proxy.get("url", proxy.get("proxy_url"))
        elif isinstance(proxy, str) and proxy.lower() not in {item.value for item in DockerProxyMode}:
            proxy_mode, proxy_url = DockerProxyMode.EXPLICIT, proxy
        else:
            proxy_mode = proxy
    if proxy_mode is None and proxy_url:
        proxy_mode = DockerProxyMode.EXPLICIT
    if proxy_mode is None:
        mode = DockerProxyMode.NONE
    elif isinstance(proxy_mode, DockerProxyMode):
        mode = proxy_mode
    else:
        mode = DockerProxyMode(str(proxy_mode).lower())
    if mode is DockerProxyMode.EXPLICIT and not proxy_url:
        raise ValueError("proxy_url is required when proxy_mode is explicit.")
    if mode is not DockerProxyMode.EXPLICIT:
        proxy_url = None
    return mode, proxy_url


def _internal_model_name(model: str) -> str:
    """Give LiteLLM an OpenAI provider prefix for bare model IDs."""

    normalized = model.strip()
    return normalized if "/" in normalized else f"openai/{normalized}"


def _model_slug(model: str, used: set[str]) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", model.strip()).strip("-.").lower() or "model"
    if slug not in used:
        return slug
    digest = hashlib.sha256(model.encode("utf-8")).hexdigest()[:8]
    return f"{slug}-{digest}"


def _merge_result(
    model: str,
    round_number: int,
    result: BenchmarkResult,
    config: CampaignConfig,
) -> dict[str, Any]:
    merged = result.to_dict()
    merged["model"] = model
    merged["round"] = round_number
    return _without_credentials(merged, config)


def _failure_record(model: str, round_number: int, exception: Exception) -> dict[str, Any]:
    return {
        "model": model,
        "round": round_number,
        "task_id": None,
        "engine": None,
        "artifact_directory": None,
        "status": None,
        "success": None,
        "metrics": {},
        "verifier": None,
        "error": str(exception) or type(exception).__name__,
    }


def _without_credentials(value: Any, config: CampaignConfig) -> Any:
    if isinstance(value, Mapping):
        return {
            key: _without_credentials(item, config)
            for key, item in value.items()
            if key not in {"api_key", "base_url", "proxy_url"}
        }
    if isinstance(value, list):
        return [_without_credentials(item, config) for item in value]
    if isinstance(value, tuple):
        return [_without_credentials(item, config) for item in value]
    if isinstance(value, str):
        result = value
        for secret in (config.api_key, config.base_url, config.proxy_url):
            if secret:
                result = result.replace(secret, "[REDACTED]")
        return result
    return value


def _scrub_tree(root: Path, config: CampaignConfig) -> None:
    for path in root.rglob("*"):
        if not path.is_file() or "workspace" in path.relative_to(root).parts:
            continue
        try:
            if path.suffix == ".json":
                payload = json.loads(path.read_text(encoding="utf-8"))
                _write_json(path, _without_credentials(payload, config))
            else:
                content = path.read_text(encoding="utf-8")
                scrubbed = _without_credentials(content, config)
                if scrubbed != content:
                    path.write_text(scrubbed, encoding="utf-8")
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def _summary_markdown(campaign: CampaignRun) -> str:
    return markdown(aggregate(list(campaign.results))) + "\n" + _legacy_summary_markdown(campaign)


def _legacy_summary_markdown(campaign: CampaignRun) -> str:
    lines = [
        "# Multi-model Paired Benchmark Campaign",
        "",
        "| Model | Round | Task | Engine | Status | Success | Steps | Total tokens | Provider/LiteLLM cost | OpenAI Standard estimate | Duration (s) |",
        "| --- | ---: | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for result in campaign.results:
        metrics = result.get("metrics") if isinstance(result.get("metrics"), Mapping) else {}
        tokens = metrics.get("tokens")
        total_tokens = tokens.get("total") if isinstance(tokens, Mapping) else None
        cost = metrics.get("cost")
        cost_text = "null" if cost is None else str(cost)
        estimate = metrics.get("openai_standard_estimated_cost_usd")
        estimate_text = "null" if estimate is None else str(estimate)
        duration = metrics.get("duration_seconds")
        duration_text = "null" if duration is None else str(duration)
        success = result.get("success")
        success_text = "null" if success is None else str(success).lower()
        lines.append(
            f"| {result.get('model', 'null')} | {result.get('round', 'null')} | "
            f"{result.get('task_id') or 'null'} | {result.get('engine') or 'null'} | "
            f"{result.get('status') or 'null'} | {success_text} | {metrics.get('steps', 'null')} | "
            f"{total_tokens if total_tokens is not None else 'null'} | {cost_text} | {estimate_text} | "
            f"{duration_text} |"
        )
    if campaign.errors:
        lines.extend(["", "## Errors", ""])
        for error in campaign.errors:
            lines.append(
                f"- {error.get('model', 'null')} round {error.get('round', 'null')}: "
                f"{error.get('error') or 'unknown error'}"
            )
    lines.extend(["", "Results are raw development evidence; no performance numbers are prefilled.", ""])
    return "\n".join(lines)


__all__ = [
    "BenchmarkRunnerCallable",
    "CampaignConfig",
    "CampaignRun",
    "CampaignRunner",
    "run_campaign",
]
