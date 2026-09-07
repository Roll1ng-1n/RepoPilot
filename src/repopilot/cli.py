"""RepoPilot's CLI entry point for a repository-scoped Agent Run."""

from __future__ import annotations

import json
import os
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

import typer
from platformdirs import user_state_dir

from repopilot.approval import ApprovalContext
from repopilot.artifacts import RunArtifacts
from repopilot.benchmark import (
    DEFAULT_BENCHMARK_IMAGE,
    BenchmarkBudget,
    BenchmarkConfig,
    BenchmarkEngine,
    BenchmarkModel,
    BenchmarkRun,
    run_benchmark,
)
from repopilot.budget import RunBudget
from repopilot.campaign import CampaignConfig, CampaignRun, run_campaign
from repopilot.checkpoint import RepositoryStateError, verify_repository_state
from repopilot.context import ContextManager, ContextStrategy, model_summary_generator
from repopilot.environment import (
    DockerProxyMode,
    EnvironmentCreationError,
    EnvironmentRequest,
    ExecutionEnvironmentFactory,
    create_execution_environment,
    validate_environment_request,
)
from repopilot.inspection import load_run_inspection, render_human
from repopilot.model import LiteLLMToolCallingModel, ToolCallingModel
from repopilot.model_probe import ProbeReport, run_model_probe
from repopilot.plan import PlanHistory, PlanInvariantError
from repopilot.runtime import AgentRuntime
from repopilot.swebench_smoke import DEFAULT_IMAGE, SWEbenchSmokeConfig, SWEbenchSmokeResult, run_swebench_smoke
from repopilot.tools import create_tool_registry


@dataclass(frozen=True)
class ModelOptions:
    model_name: str | None
    api_key: str | None
    base_url: str | None
    model_kwargs: dict[str, Any] = field(default_factory=dict)


ModelFactory = Callable[[ModelOptions], ToolCallingModel]
BenchmarkRunner = Callable[[BenchmarkConfig], BenchmarkRun]
SmokeRunner = Callable[[SWEbenchSmokeConfig], SWEbenchSmokeResult]
ProbeRunner = Callable[..., ProbeReport]
CampaignExecutor = Callable[[CampaignConfig], CampaignRun]

_BUILTIN_BENCHMARK_TASKS = Path(__file__).with_name("benchmark_tasks")


class EnvironmentOption(str, Enum):
    """Execution Environment choices exposed by the product CLI."""

    LOCAL = "local"
    DOCKER = "docker"


def create_app(
    model_factory: ModelFactory | None = None,
    environment_factory: ExecutionEnvironmentFactory | None = None,
    *,
    sleeper: Callable[[float], None] | None = None,
    benchmark_runner: BenchmarkRunner | None = None,
    probe_runner: ProbeRunner | None = None,
    campaign_runner: CampaignExecutor | None = None,
    smoke_runner: SmokeRunner | None = None,
    swebench_smoke_runner: SmokeRunner | None = None,
) -> typer.Typer:
    """Build the CLI, allowing Runtime Tests to replace composition boundaries."""

    app = typer.Typer(add_completion=False, help="Run RepoPilot against a Target Repository.")
    selected_model_factory = model_factory or _create_litellm_model
    selected_environment_factory = environment_factory or create_execution_environment
    selected_benchmark_runner = benchmark_runner or run_benchmark
    selected_probe_runner = probe_runner or run_model_probe
    selected_campaign_runner = campaign_runner or run_campaign
    selected_smoke_runner = smoke_runner or swebench_smoke_runner

    def print_result(result: Any) -> None:
        typer.echo(f"Agent Run {result.run_id}: {result.status}")
        typer.echo(f"Plan v{result.plan.version}")
        for step in result.plan.steps:
            typer.echo(f"- [{step.status.value}] {step.description}")
        typer.echo(f"Artifacts: {result.artifact_directory}")

    @app.callback()
    def main() -> None:
        """RepoPilot commands."""

    @app.command()
    def run(
        repository: Path = typer.Argument(..., exists=True, file_okay=False, resolve_path=True),
        task: str | None = typer.Option(None, "--task", "-t"),
        state_dir: Path | None = typer.Option(None, "--state-dir", file_okay=False),
        model: str | None = typer.Option(None, "--model", envvar="REPOPILOT_MODEL"),
        api_key: str | None = typer.Option(None, "--api-key", envvar="REPOPILOT_API_KEY", show_default=False),
        base_url: str | None = typer.Option(None, "--base-url", envvar="REPOPILOT_BASE_URL"),
        environment_name: EnvironmentOption = typer.Option(
            EnvironmentOption.LOCAL,
            "--environment",
            help="Execution Environment.",
        ),
        image: str | None = typer.Option(None, "--image", help="Container image required by --environment docker."),
        docker_proxy_mode: DockerProxyMode = typer.Option(
            DockerProxyMode.NONE,
            "--docker-proxy-mode",
            envvar="REPOPILOT_DOCKER_PROXY_MODE",
            help="Container proxy policy: none, inherit, or explicit.",
        ),
        docker_proxy_url: str | None = typer.Option(
            None,
            "--docker-proxy-url",
            envvar="REPOPILOT_DOCKER_PROXY_URL",
            show_default=False,
            help="Container proxy URL required by --docker-proxy-mode explicit.",
        ),
        max_steps: int = typer.Option(30, "--max-steps", min=1),
        max_replans: int = typer.Option(2, "--max-replans", min=0),
        max_consecutive_failures: int = typer.Option(3, "--max-consecutive-failures", min=1),
        command_timeout_seconds: float = typer.Option(300.0, "--command-timeout-seconds", min=0.001),
        max_run_seconds: float = typer.Option(30.0 * 60.0, "--max-run-seconds", min=0.001),
        context_strategy: ContextStrategy = typer.Option(ContextStrategy.NONE, "--context-strategy"),
        context_max_characters: int = typer.Option(12_000, "--context-max-characters", min=1),
        auto_approve_disposable_docker_benchmark: bool = typer.Option(
            False,
            "--auto-approve-disposable-docker-benchmark",
            help="Auto-approve high-risk calls only for an explicitly disposable Docker benchmark.",
        ),
    ) -> None:
        if task is None:
            task = typer.prompt("Task")
        request = EnvironmentRequest(
            target_repository=repository,
            environment=environment_name.value,
            image=image,
            proxy_mode=docker_proxy_mode,
            proxy_url=docker_proxy_url,
        )
        try:
            validate_environment_request(request)
        except ValueError as error:
            if docker_proxy_mode is DockerProxyMode.EXPLICIT and not docker_proxy_url:
                parameter = "--docker-proxy-url"
            elif environment_name is EnvironmentOption.DOCKER and not image:
                parameter = "--image"
            else:
                parameter = "--environment"
            raise typer.BadParameter(str(error), param_hint=parameter) from error
        if auto_approve_disposable_docker_benchmark and environment_name is not EnvironmentOption.DOCKER:
            raise typer.BadParameter(
                "Automatic approval is available only for an explicitly disposable Docker benchmark.",
                param_hint="--auto-approve-disposable-docker-benchmark",
            )
        options = ModelOptions(model_name=model, api_key=api_key, base_url=base_url)
        try:
            tool_calling_model = selected_model_factory(options)
        except ValueError as error:
            raise typer.BadParameter(str(error), param_hint="--model") from error
        try:
            execution_environment = selected_environment_factory(request)
        except ValueError as error:
            parameter = "--image" if environment_name is EnvironmentOption.DOCKER and not image else "--environment"
            raise typer.BadParameter(str(error), param_hint=parameter) from error
        except EnvironmentCreationError as error:
            typer.echo(f"Error: {error}", err=True)
            raise typer.Exit(code=1) from error
        if environment_name is EnvironmentOption.LOCAL:
            typer.echo("Warning: Local Environment executes commands directly in the Target Repository.")
        else:
            typer.echo(
                "Docker Environment runs commands in a container with the Target Repository bind-mounted at "
                "/workspace; it is not a security boundary."
            )
        secret_values = _credential_values(api_key)
        artifacts = RunArtifacts(state_dir or Path(user_state_dir("repopilot")) / "runs", secrets=secret_values)
        plan_history = PlanHistory.for_task(task)
        budget = RunBudget(
            max_steps=max_steps,
            max_replans=max_replans,
            max_consecutive_failures=max_consecutive_failures,
            command_timeout_seconds=command_timeout_seconds,
            max_run_seconds=max_run_seconds,
        )
        verifications: list[dict[str, Any]] = []
        context = ContextManager(
            context_strategy,
            max_characters=context_max_characters,
            summarizer=model_summary_generator(tool_calling_model)
            if context_strategy is ContextStrategy.SUMMARY
            else None,
        )
        try:
            result = AgentRuntime(
                tool_calling_model,
                create_tool_registry(
                    execution_environment,
                    repository,
                    plan_history,
                    command_timeout_seconds=budget.command_timeout_seconds,
                    verifications=verifications,
                ),
                artifacts,
                plan_history,
                budget,
                sleeper,
                checkpoint_model={
                    "backend": "litellm",
                    "model_name": tool_calling_model.model_name,
                    "base_url": base_url,
                },
                checkpoint_environment={
                    "backend": request.environment,
                    "image": request.image,
                    **(
                        {"proxy_mode": request.proxy_mode.value}
                        if request.environment == EnvironmentOption.DOCKER.value
                        else {}
                    ),
                },
                verifications=verifications,
                context=context,
                approval_context=ApprovalContext(
                    environment=request.environment,
                    disposable_benchmark=auto_approve_disposable_docker_benchmark,
                    automatic_approval=auto_approve_disposable_docker_benchmark,
                ),
            ).run(task, repository)
        finally:
            execution_environment.close()
        print_result(result)

    @app.command()
    def inspect(
        run_id: str = typer.Argument(..., help="The persisted Agent Run ID."),
        state_dir: Path | None = typer.Option(None, "--state-dir", file_okay=False),
        json_output: bool = typer.Option(False, "--json", help="Print one machine-readable JSON inspection document."),
    ) -> None:
        """Inspect a persisted Agent Run without resuming or executing it."""

        run_state_directory = state_dir or Path(user_state_dir("repopilot")) / "runs"
        try:
            inspection = load_run_inspection(run_state_directory, run_id)
        except (FileNotFoundError, OSError, ValueError) as error:
            typer.echo(f"Error: {error}", err=True)
            raise typer.Exit(code=1) from error
        if json_output:
            typer.echo(json.dumps(inspection.to_dict(), indent=2, sort_keys=True))
        else:
            typer.echo(render_human(inspection), nl=False)

    @app.command()
    def benchmark(
        repeats: int = typer.Option(3, "--repeats", min=1),
        state_dir: Path | None = typer.Option(None, "--state-dir", file_okay=False),
        tasks_dir: Path = typer.Option(
            _BUILTIN_BENCHMARK_TASKS,
            "--tasks-dir",
            exists=True,
            file_okay=False,
            resolve_path=True,
            help="Directory containing fixed benchmark task manifests.",
        ),
        engines: list[BenchmarkEngine] = typer.Option(
            [BenchmarkEngine.BASELINE, BenchmarkEngine.REPOPILOT],
            "--engine",
            help="Engine to run; repeat to compare multiple engines.",
        ),
        tasks: list[str] = typer.Option(
            [],
            "--task",
            help="Task ID to run; repeat to select multiple fixed tasks.",
        ),
        model: str | None = typer.Option(None, "--model", envvar="REPOPILOT_MODEL"),
        api_key: str | None = typer.Option(None, "--api-key", envvar="REPOPILOT_API_KEY", show_default=False),
        base_url: str | None = typer.Option(None, "--base-url", envvar="REPOPILOT_BASE_URL"),
        image: str = typer.Option(DEFAULT_BENCHMARK_IMAGE, "--image", help="Docker image shared by both engines."),
        docker_proxy_mode: DockerProxyMode = typer.Option(
            DockerProxyMode.NONE,
            "--docker-proxy-mode",
            envvar="REPOPILOT_DOCKER_PROXY_MODE",
            help="Shared container proxy policy for both benchmark engines.",
        ),
        docker_proxy_url: str | None = typer.Option(
            None,
            "--docker-proxy-url",
            envvar="REPOPILOT_DOCKER_PROXY_URL",
            show_default=False,
            help="Shared proxy URL required by --docker-proxy-mode explicit.",
        ),
        temperature: float = typer.Option(0.0, "--temperature"),
        max_steps: int = typer.Option(15, "--max-steps", min=1),
        max_replans: int = typer.Option(1, "--max-replans", min=0),
        max_consecutive_failures: int = typer.Option(2, "--max-consecutive-failures", min=1),
        command_timeout_seconds: float = typer.Option(30.0, "--command-timeout-seconds", min=0.001),
        max_run_seconds: float = typer.Option(180.0, "--max-run-seconds", min=0.001),
        stream: bool = typer.Option(
            False,
            "--stream",
            help="Force streaming requests (for accounts restricted to streaming).",
        ),
    ) -> None:
        """Compare the mini-SWE-agent baseline and RepoPilot on fixed Docker tasks."""

        if not model:
            raise typer.BadParameter("Provide --model or set REPOPILOT_MODEL.", param_hint="--model")
        if not engines:
            raise typer.BadParameter("Select at least one benchmark engine.", param_hint="--engine")
        benchmark_root = state_dir or Path(user_state_dir("repopilot")) / "benchmarks"
        output_directory = benchmark_root.resolve() / uuid.uuid4().hex
        try:
            model_kwargs: dict[str, Any] = {"temperature": temperature}
            if stream:
                model_kwargs["stream"] = True
            config = BenchmarkConfig(
                tasks_directory=tasks_dir,
                output_directory=output_directory,
                repeats=repeats,
                model=BenchmarkModel(
                    model_name=model,
                    model_kwargs=model_kwargs,
                    api_key=api_key,
                    base_url=base_url,
                ),
                image=image,
                proxy_mode=docker_proxy_mode,
                proxy_url=docker_proxy_url,
                budget=BenchmarkBudget(
                    max_steps=max_steps,
                    max_replans=max_replans,
                    max_consecutive_failures=max_consecutive_failures,
                    command_timeout_seconds=command_timeout_seconds,
                    max_run_seconds=max_run_seconds,
                ),
                engines=tuple(dict.fromkeys(engines)),
                task_ids=tuple(dict.fromkeys(tasks)),
            )
        except ValueError as error:
            raise typer.BadParameter(str(error), param_hint="--docker-proxy-url") from error
        try:
            benchmark_run = selected_benchmark_runner(config)
        except (FileNotFoundError, OSError, RuntimeError, ValueError) as error:
            typer.echo(f"Error: {error}", err=True)
            raise typer.Exit(code=1) from error

        typer.echo(f"Agent Benchmark: {benchmark_run.output_directory}")
        for item in benchmark_run.results:
            success = "passed" if item.success else "failed" if item.success is False else "unknown"
            typer.echo(
                f"- {item.task_id} / {item.engine.value}: repository {success}; "
                f"behavior={item.evaluation.get('behavior_pass')}; task={item.evaluation.get('task_pass')} "
                f"(Agent Run: {item.status or 'unknown'}, repeat={item.repeat})"
            )
        typer.echo(f"Summary: {benchmark_run.output_directory / 'summary.json'}")

    @app.command("probe")
    def probe_models(
        models: list[str] = typer.Option([], "--model", help="Model ID to probe; repeat for multiple models."),
        state_dir: Path | None = typer.Option(None, "--state-dir", file_okay=False),
        api_key: str | None = typer.Option(None, "--api-key", envvar="REPOPILOT_API_KEY", show_default=False),
        base_url: str | None = typer.Option(None, "--base-url", envvar="REPOPILOT_BASE_URL"),
        env_file: Path | None = typer.Option(
            Path(".env"),
            "--env-file",
            dir_okay=False,
            help="Optional dotenv file used only for missing API credentials.",
        ),
        temperature: float | None = typer.Option(
            None,
            "--temperature",
            help="Optional compatibility parameter; omitted by default.",
        ),
    ) -> None:
        """Probe text and required native Tool Calling before paid Agent Runs."""

        selected_models = tuple(dict.fromkeys(model.strip() for model in models if model.strip()))
        if not selected_models:
            raise typer.BadParameter("Provide at least one --model.", param_hint="--model")
        api_key, base_url = _credentials_from_env_file(api_key, base_url, env_file)
        if not api_key:
            raise typer.BadParameter(
                "Provide --api-key, set REPOPILOT_API_KEY, or configure it in --env-file.",
                param_hint="--api-key",
            )
        request_kwargs = {} if temperature is None else {"temperature": temperature}
        report = selected_probe_runner(
            selected_models,
            api_key=api_key,
            base_url=base_url,
            request_kwargs=request_kwargs,
        )
        output_root = (state_dir or Path(user_state_dir("repopilot")) / "model-probes").resolve()
        output_directory = output_root / uuid.uuid4().hex
        report.write_json(output_directory / "summary.json")
        report.write_markdown(output_directory / "summary.md")
        typer.echo(f"Model Probe: {output_directory}")
        for result in report.results:
            typer.echo(f"- {result.model}: {'passed' if result.passed else 'failed'}")
        typer.echo(f"Summary: {output_directory / 'summary.json'}")
        if not all(result.passed for result in report.results):
            raise typer.Exit(code=1)

    @app.command("campaign")
    def benchmark_campaign(
        models: list[str] = typer.Option([], "--model", help="Model ID to run; repeat for multiple models."),
        rounds: int = typer.Option(3, "--rounds", "--repeats", min=1),
        state_dir: Path | None = typer.Option(None, "--state-dir", file_okay=False),
        tasks_dir: Path = typer.Option(
            _BUILTIN_BENCHMARK_TASKS,
            "--tasks-dir",
            exists=True,
            file_okay=False,
            resolve_path=True,
        ),
        engines: list[BenchmarkEngine] = typer.Option(
            [BenchmarkEngine.BASELINE, BenchmarkEngine.REPOPILOT],
            "--engine",
        ),
        tasks: list[str] = typer.Option([], "--task", help="Task ID to run; repeat for multiple tasks."),
        api_key: str | None = typer.Option(None, "--api-key", envvar="REPOPILOT_API_KEY", show_default=False),
        base_url: str | None = typer.Option(None, "--base-url", envvar="REPOPILOT_BASE_URL"),
        env_file: Path | None = typer.Option(
            Path(".env"),
            "--env-file",
            dir_okay=False,
            help="Optional dotenv file used only for missing API credentials.",
        ),
        image: str = typer.Option(DEFAULT_BENCHMARK_IMAGE, "--image"),
        docker_proxy_mode: DockerProxyMode = typer.Option(
            DockerProxyMode.NONE,
            "--docker-proxy-mode",
            envvar="REPOPILOT_DOCKER_PROXY_MODE",
        ),
        docker_proxy_url: str | None = typer.Option(
            None,
            "--docker-proxy-url",
            envvar="REPOPILOT_DOCKER_PROXY_URL",
            show_default=False,
        ),
        temperature: float = typer.Option(0.0, "--temperature"),
        max_steps: int = typer.Option(15, "--max-steps", min=1),
        max_replans: int = typer.Option(1, "--max-replans", min=0),
        max_consecutive_failures: int = typer.Option(2, "--max-consecutive-failures", min=1),
        command_timeout_seconds: float = typer.Option(30.0, "--command-timeout-seconds", min=0.001),
        max_run_seconds: float = typer.Option(180.0, "--max-run-seconds", min=0.001),
        stream: bool = typer.Option(
            False,
            "--stream",
            help="Force streaming requests (for accounts restricted to streaming).",
        ),
    ) -> None:
        """Run a sequential multi-model campaign using the paired Agent Benchmark."""

        selected_models = tuple(dict.fromkeys(model.strip() for model in models if model.strip()))
        if not selected_models:
            raise typer.BadParameter("Provide at least one --model.", param_hint="--model")
        if not engines:
            raise typer.BadParameter("Select at least one benchmark engine.", param_hint="--engine")
        api_key, base_url = _credentials_from_env_file(api_key, base_url, env_file)
        if not api_key:
            raise typer.BadParameter(
                "Provide --api-key, set REPOPILOT_API_KEY, or configure it in --env-file.",
                param_hint="--api-key",
            )
        output_root = (state_dir or Path(user_state_dir("repopilot")) / "campaigns").resolve()
        output_directory = output_root / uuid.uuid4().hex
        try:
            config = CampaignConfig(
                output_directory=output_directory,
                tasks_directory=tasks_dir,
                models=selected_models,
                rounds=rounds,
                image=image,
                budget=BenchmarkBudget(
                    max_steps=max_steps,
                    max_replans=max_replans,
                    max_consecutive_failures=max_consecutive_failures,
                    command_timeout_seconds=command_timeout_seconds,
                    max_run_seconds=max_run_seconds,
                ),
                engines=tuple(dict.fromkeys(engines)),
                task_ids=tuple(dict.fromkeys(tasks)),
                temperature=temperature,
                stream=stream,
                api_key=api_key,
                base_url=base_url,
                proxy_mode=docker_proxy_mode,
                proxy_url=docker_proxy_url,
            )
            campaign_run = selected_campaign_runner(config)
        except ValueError as error:
            raise typer.BadParameter(str(error)) from error
        typer.echo(f"Benchmark Campaign: {campaign_run.output_directory}")
        typer.echo(f"Samples: {len(campaign_run.results)}; batch errors: {len(campaign_run.errors)}")
        typer.echo(f"Summary: {campaign_run.output_directory / 'summary.json'}")

    @app.command("swebench-smoke")
    def swebench_smoke(
        state_dir: Path | None = typer.Option(None, "--state-dir", file_okay=False),
        model: str | None = typer.Option(None, "--model", envvar="REPOPILOT_MODEL"),
        api_key: str | None = typer.Option(None, "--api-key", envvar="REPOPILOT_API_KEY", show_default=False),
        base_url: str | None = typer.Option(None, "--base-url", envvar="REPOPILOT_BASE_URL"),
        image: str = typer.Option(
            DEFAULT_IMAGE, "--image", help="Locally available Docker image for the pinned SWE-bench instance."
        ),
        temperature: float = typer.Option(0.0, "--temperature"),
        max_steps: int = typer.Option(50, "--max-steps", min=1),
        max_replans: int = typer.Option(2, "--max-replans", min=0),
        max_consecutive_failures: int = typer.Option(3, "--max-consecutive-failures", min=1),
        command_timeout_seconds: float = typer.Option(300.0, "--command-timeout-seconds", min=0.001),
        max_run_seconds: float = typer.Option(30.0 * 60.0, "--max-run-seconds", min=0.001),
        max_cost_usd: float = typer.Option(3.0, "--max-cost-usd", min=0.0),
        verifier_timeout_seconds: float = typer.Option(30.0 * 60.0, "--verifier-timeout-seconds", min=0.001),
        docker_executable: str | None = typer.Option(None, "--docker-executable", envvar="MSWEA_DOCKER_EXECUTABLE"),
    ) -> None:
        """Run the one pinned SWE-bench Lite smoke and retain its artifacts."""

        smoke_root = state_dir or Path(user_state_dir("repopilot")) / "swebench-smoke"
        output_directory = smoke_root.resolve() / uuid.uuid4().hex
        config_kwargs: dict[str, Any] = {
            "output_directory": output_directory,
            "model_name": model or "unspecified",
            "model_kwargs": {"temperature": temperature},
            "image": image,
            "max_steps": max_steps,
            "max_replans": max_replans,
            "max_consecutive_failures": max_consecutive_failures,
            "command_timeout_seconds": command_timeout_seconds,
            "max_run_seconds": max_run_seconds,
            "max_cost_usd": max_cost_usd,
            "verifier_timeout_seconds": verifier_timeout_seconds,
        }
        if docker_executable is not None:
            config_kwargs["docker_executable"] = docker_executable
        try:
            config = SWEbenchSmokeConfig(**config_kwargs)
        except ValueError as error:
            raise typer.BadParameter(str(error)) from error

        smoke_model_factory = None
        if model:
            options = ModelOptions(
                model_name=model,
                api_key=api_key,
                base_url=base_url,
                model_kwargs=dict(config.model_kwargs),
            )

            def create_smoke_model(_instance: dict[str, Any]) -> ToolCallingModel:
                return selected_model_factory(options)

            smoke_model_factory = create_smoke_model

        try:
            smoke_result = (
                selected_smoke_runner(config)
                if selected_smoke_runner is not None
                else run_swebench_smoke(config, model_factory=smoke_model_factory)
            )
        except (FileNotFoundError, OSError, RuntimeError, ValueError) as error:
            typer.echo(f"Error: {error}", err=True)
            typer.echo(f"Artifacts: {output_directory}")
            raise typer.Exit(code=1) from error

        typer.echo(f"SWE-bench Smoke: {smoke_result.status}")
        typer.echo(f"Instance: {smoke_result.instance_id}")
        typer.echo(f"Artifacts: {smoke_result.artifact_directory}")
        if smoke_result.success is not None:
            typer.echo(f"Success: {smoke_result.success}")
        if smoke_result.error:
            typer.echo(f"Error: {smoke_result.error}")

    def _resume(
        run_id: str = typer.Argument(..., help="The persisted Agent Run ID."),
        state_dir: Path | None = typer.Option(None, "--state-dir", file_okay=False),
        model: str | None = typer.Option(None, "--model", envvar="REPOPILOT_MODEL"),
        api_key: str | None = typer.Option(None, "--api-key", envvar="REPOPILOT_API_KEY", show_default=False),
        base_url: str | None = typer.Option(None, "--base-url", envvar="REPOPILOT_BASE_URL"),
        docker_proxy_url: str | None = None,
        approval_granted: bool | None = None,
    ) -> None:
        """Resume a STOPPED Agent Run or resolve one pending Human Approval."""

        run_state_directory = state_dir or Path(user_state_dir("repopilot")) / "runs"
        try:
            artifacts = RunArtifacts.reopen(run_state_directory, run_id, secrets=_credential_values(api_key))
            checkpoint = artifacts.read_checkpoint()
        except (FileNotFoundError, ValueError) as error:
            typer.echo(f"Error: {error}", err=True)
            raise typer.Exit(code=1) from error

        if checkpoint.get("run_id") != run_id:
            typer.echo(f"Error: Agent Run {run_id} has an invalid Checkpoint Run ID.", err=True)
            raise typer.Exit(code=1)
        status = checkpoint.get("status")
        if approval_granted is None:
            if status == "WAITING_FOR_APPROVAL":
                typer.echo(f"Agent Run {run_id} is still waiting for Human Approval.")
                return
            if status != "STOPPED":
                typer.echo(f"Error: Agent Run {run_id} cannot resume from {status!r}.", err=True)
                raise typer.Exit(code=1)
        elif status != "WAITING_FOR_APPROVAL":
            typer.echo(f"Error: Agent Run {run_id} has no pending Human Approval.", err=True)
            raise typer.Exit(code=1)

        try:
            repository_state = _checkpoint_mapping(checkpoint, "repository")
            target_repository = Path(_checkpoint_string(repository_state, "resolved_target_repository"))
            environment_state = _checkpoint_mapping(checkpoint, "environment")
            proxy_mode = environment_state.get("proxy_mode", DockerProxyMode.NONE.value)
            request = EnvironmentRequest(
                target_repository=target_repository,
                environment=_checkpoint_string(environment_state, "backend"),
                image=environment_state.get("image") if isinstance(environment_state.get("image"), str) else None,
                proxy_mode=proxy_mode,
                proxy_url=docker_proxy_url if proxy_mode == DockerProxyMode.EXPLICIT.value else None,
            )
            validate_environment_request(request)
            plan_history_value = checkpoint.get("plan_history")
            if not isinstance(plan_history_value, list):
                raise ValueError("Checkpoint has invalid Plan History.")
            plan_history = PlanHistory.from_dict(plan_history_value)
            budget = _budget_from_checkpoint(_checkpoint_mapping(checkpoint, "budget"))
            verifications = checkpoint.get("verifications")
            if not isinstance(verifications, list):
                raise ValueError("Checkpoint has invalid Task Verifications.")
            context_state = checkpoint.get("context")
            if context_state is not None and not isinstance(context_state, dict):
                raise ValueError("Checkpoint has invalid Context state.")
            approval_context_value = checkpoint.get("approval_context")
            approval_context = (
                ApprovalContext(environment=request.environment)
                if approval_context_value is None
                else ApprovalContext.from_dict(_checkpoint_mapping(checkpoint, "approval_context"))
            )
            if approval_context.environment != request.environment:
                raise ValueError("Checkpoint Approval Context does not match its Execution Environment.")
        except (KeyError, TypeError, ValueError, PlanInvariantError) as error:
            typer.echo(f"Error: {error}", err=True)
            raise typer.Exit(code=1) from error

        try:
            execution_environment = selected_environment_factory(request)
        except ValueError as error:
            typer.echo(f"Error: {error}", err=True)
            raise typer.Exit(code=1) from error
        except EnvironmentCreationError as error:
            typer.echo(f"Error: {error}", err=True)
            raise typer.Exit(code=1) from error
        try:
            verify_repository_state(repository_state, target_repository)
            model_state = _checkpoint_mapping(checkpoint, "model")
            options = ModelOptions(
                model_name=model or _checkpoint_string(model_state, "model_name"),
                api_key=api_key,
                base_url=base_url if base_url is not None else model_state.get("base_url"),
            )
            tool_calling_model = selected_model_factory(options)
            context = ContextManager(summarizer=model_summary_generator(tool_calling_model))
            result = AgentRuntime(
                tool_calling_model,
                create_tool_registry(
                    execution_environment,
                    target_repository,
                    plan_history,
                    command_timeout_seconds=budget.command_timeout_seconds,
                    verifications=verifications,
                ),
                artifacts,
                plan_history,
                budget,
                sleeper,
                checkpoint_model=model_state,
                checkpoint_environment=environment_state,
                verifications=verifications,
                context=context,
                approval_context=approval_context,
            ).resume(checkpoint, target_repository, approval_granted=approval_granted)
        except (RepositoryStateError, ValueError) as error:
            typer.echo(f"Error: {error}", err=True)
            raise typer.Exit(code=1) from error
        finally:
            execution_environment.close()
        print_result(result)

    @app.command()
    def resume(
        run_id: str = typer.Argument(..., help="The persisted Agent Run ID."),
        state_dir: Path | None = typer.Option(None, "--state-dir", file_okay=False),
        model: str | None = typer.Option(None, "--model", envvar="REPOPILOT_MODEL"),
        api_key: str | None = typer.Option(None, "--api-key", envvar="REPOPILOT_API_KEY", show_default=False),
        base_url: str | None = typer.Option(None, "--base-url", envvar="REPOPILOT_BASE_URL"),
        docker_proxy_url: str | None = typer.Option(
            None,
            "--docker-proxy-url",
            envvar="REPOPILOT_DOCKER_PROXY_URL",
            show_default=False,
            help="Re-supply an explicit container proxy URL; URLs are not stored in Checkpoints.",
        ),
    ) -> None:
        """Resume a STOPPED Agent Run after recreating its Execution Environment."""

        _resume(run_id, state_dir, model, api_key, base_url, docker_proxy_url)

    @app.command()
    def approve(
        run_id: str = typer.Argument(..., help="The Agent Run waiting for Human Approval."),
        state_dir: Path | None = typer.Option(None, "--state-dir", file_okay=False),
        model: str | None = typer.Option(None, "--model", envvar="REPOPILOT_MODEL"),
        api_key: str | None = typer.Option(None, "--api-key", envvar="REPOPILOT_API_KEY", show_default=False),
        base_url: str | None = typer.Option(None, "--base-url", envvar="REPOPILOT_BASE_URL"),
        docker_proxy_url: str | None = typer.Option(
            None,
            "--docker-proxy-url",
            envvar="REPOPILOT_DOCKER_PROXY_URL",
            show_default=False,
        ),
    ) -> None:
        """Approve the persisted high-risk Tool Call, then resume the Agent Run."""

        _resume(run_id, state_dir, model, api_key, base_url, docker_proxy_url, approval_granted=True)

    @app.command()
    def reject(
        run_id: str = typer.Argument(..., help="The Agent Run waiting for Human Approval."),
        state_dir: Path | None = typer.Option(None, "--state-dir", file_okay=False),
        model: str | None = typer.Option(None, "--model", envvar="REPOPILOT_MODEL"),
        api_key: str | None = typer.Option(None, "--api-key", envvar="REPOPILOT_API_KEY", show_default=False),
        base_url: str | None = typer.Option(None, "--base-url", envvar="REPOPILOT_BASE_URL"),
        docker_proxy_url: str | None = typer.Option(
            None,
            "--docker-proxy-url",
            envvar="REPOPILOT_DOCKER_PROXY_URL",
            show_default=False,
        ),
    ) -> None:
        """Reject the persisted high-risk Tool Call and let the model revise its plan."""

        _resume(run_id, state_dir, model, api_key, base_url, docker_proxy_url, approval_granted=False)

    return app


def _create_litellm_model(options: ModelOptions) -> ToolCallingModel:
    if not options.model_name:
        raise ValueError("Provide --model or set REPOPILOT_MODEL.")
    return LiteLLMToolCallingModel(
        model_name=options.model_name,
        api_key=options.api_key,
        base_url=options.base_url,
        model_kwargs=options.model_kwargs,
    )


def _credential_values(api_key: str | None) -> list[str]:
    values = [api_key] if api_key else []
    for name, value in os.environ.items():
        if any(marker in name.upper() for marker in ("KEY", "TOKEN", "SECRET", "PASSWORD")):
            values.append(value)
    return values


def _credentials_from_env_file(
    api_key: str | None,
    base_url: str | None,
    env_file: Path | None,
) -> tuple[str | None, str | None]:
    """Fill missing model credentials from one local dotenv file without mutating the process."""

    if env_file is None or not env_file.is_file() or (api_key is not None and base_url is not None):
        return api_key, base_url
    from dotenv import dotenv_values

    values = dotenv_values(env_file)
    env_api_key = values.get("REPOPILOT_API_KEY")
    env_base_url = values.get("REPOPILOT_BASE_URL")
    return (
        api_key or (env_api_key if isinstance(env_api_key, str) and env_api_key else None),
        base_url or (env_base_url if isinstance(env_base_url, str) and env_base_url else None),
    )


def _checkpoint_mapping(checkpoint: dict[str, Any], key: str) -> dict[str, Any]:
    value = checkpoint.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"Checkpoint has invalid {key}.")
    return value


def _checkpoint_string(value: dict[str, Any], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item:
        raise ValueError(f"Checkpoint has invalid {key}.")
    return item


def _budget_from_checkpoint(value: dict[str, Any]) -> RunBudget:
    try:
        return RunBudget(
            max_steps=int(value["max_steps"]),
            max_replans=int(value["max_replans"]),
            max_consecutive_failures=int(value["max_consecutive_failures"]),
            command_timeout_seconds=float(value["command_timeout_seconds"]),
            max_run_seconds=float(value["max_run_seconds"]),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("Checkpoint has invalid Run Budget.") from error


app = create_app()
