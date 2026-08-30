"""RepoPilot's CLI entry point for a repository-scoped Agent Run."""

from __future__ import annotations

import json
import os
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

import typer
from platformdirs import user_state_dir

from repopilot.approval import ApprovalContext
from repopilot.artifacts import RunArtifacts
from repopilot.benchmark import (
    BenchmarkBudget,
    BenchmarkConfig,
    BenchmarkEngine,
    BenchmarkModel,
    BenchmarkRun,
    run_benchmark,
)
from repopilot.budget import RunBudget
from repopilot.checkpoint import RepositoryStateError, verify_repository_state
from repopilot.context import ContextManager, ContextStrategy, model_summary_generator
from repopilot.environment import (
    EnvironmentCreationError,
    EnvironmentRequest,
    ExecutionEnvironmentFactory,
    create_execution_environment,
    validate_environment_request,
)
from repopilot.inspection import load_run_inspection, render_human
from repopilot.model import LiteLLMToolCallingModel, ToolCallingModel
from repopilot.plan import PlanHistory, PlanInvariantError
from repopilot.runtime import AgentRuntime
from repopilot.tools import create_tool_registry


@dataclass(frozen=True)
class ModelOptions:
    model_name: str | None
    api_key: str | None
    base_url: str | None


ModelFactory = Callable[[ModelOptions], ToolCallingModel]
BenchmarkRunner = Callable[[BenchmarkConfig], BenchmarkRun]

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
) -> typer.Typer:
    """Build the CLI, allowing Runtime Tests to replace composition boundaries."""

    app = typer.Typer(add_completion=False, help="Run RepoPilot against a Target Repository.")
    selected_model_factory = model_factory or _create_litellm_model
    selected_environment_factory = environment_factory or create_execution_environment
    selected_benchmark_runner = benchmark_runner or run_benchmark

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
        request = EnvironmentRequest(target_repository=repository, environment=environment_name.value, image=image)
        try:
            validate_environment_request(request)
        except ValueError as error:
            parameter = "--image" if environment_name is EnvironmentOption.DOCKER and not image else "--environment"
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
                checkpoint_environment={"backend": request.environment, "image": request.image},
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
        model: str | None = typer.Option(None, "--model", envvar="REPOPILOT_MODEL"),
        api_key: str | None = typer.Option(None, "--api-key", envvar="REPOPILOT_API_KEY", show_default=False),
        base_url: str | None = typer.Option(None, "--base-url", envvar="REPOPILOT_BASE_URL"),
        image: str = typer.Option("python:3.12-slim", "--image", help="Docker image shared by both engines."),
        temperature: float = typer.Option(0.0, "--temperature"),
        max_steps: int = typer.Option(15, "--max-steps", min=1),
        max_replans: int = typer.Option(1, "--max-replans", min=0),
        max_consecutive_failures: int = typer.Option(2, "--max-consecutive-failures", min=1),
        command_timeout_seconds: float = typer.Option(30.0, "--command-timeout-seconds", min=0.001),
        max_run_seconds: float = typer.Option(180.0, "--max-run-seconds", min=0.001),
    ) -> None:
        """Compare the mini-SWE-agent baseline and RepoPilot on fixed Docker tasks."""

        if not model:
            raise typer.BadParameter("Provide --model or set REPOPILOT_MODEL.", param_hint="--model")
        if not engines:
            raise typer.BadParameter("Select at least one benchmark engine.", param_hint="--engine")
        benchmark_root = state_dir or Path(user_state_dir("repopilot")) / "benchmarks"
        output_directory = benchmark_root.resolve() / uuid.uuid4().hex
        config = BenchmarkConfig(
            tasks_directory=tasks_dir,
            output_directory=output_directory,
            model=BenchmarkModel(
                model_name=model,
                model_kwargs={"temperature": temperature},
                api_key=api_key,
                base_url=base_url,
            ),
            image=image,
            budget=BenchmarkBudget(
                max_steps=max_steps,
                max_replans=max_replans,
                max_consecutive_failures=max_consecutive_failures,
                command_timeout_seconds=command_timeout_seconds,
                max_run_seconds=max_run_seconds,
            ),
            engines=tuple(dict.fromkeys(engines)),
        )
        try:
            benchmark_run = selected_benchmark_runner(config)
        except (FileNotFoundError, OSError, RuntimeError, ValueError) as error:
            typer.echo(f"Error: {error}", err=True)
            raise typer.Exit(code=1) from error

        typer.echo(f"Agent Benchmark: {benchmark_run.output_directory}")
        for item in benchmark_run.results:
            success = "passed" if item.success else "failed" if item.success is False else "unknown"
            typer.echo(f"- {item.task_id} / {item.engine.value}: {success} (Agent Run: {item.status or 'unknown'})")
        typer.echo(f"Summary: {benchmark_run.output_directory / 'summary.json'}")

    def _resume(
        run_id: str = typer.Argument(..., help="The persisted Agent Run ID."),
        state_dir: Path | None = typer.Option(None, "--state-dir", file_okay=False),
        model: str | None = typer.Option(None, "--model", envvar="REPOPILOT_MODEL"),
        api_key: str | None = typer.Option(None, "--api-key", envvar="REPOPILOT_API_KEY", show_default=False),
        base_url: str | None = typer.Option(None, "--base-url", envvar="REPOPILOT_BASE_URL"),
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
            request = EnvironmentRequest(
                target_repository=target_repository,
                environment=_checkpoint_string(environment_state, "backend"),
                image=environment_state.get("image") if isinstance(environment_state.get("image"), str) else None,
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
    ) -> None:
        """Resume a STOPPED Agent Run after recreating its Execution Environment."""

        _resume(run_id, state_dir, model, api_key, base_url)

    @app.command()
    def approve(
        run_id: str = typer.Argument(..., help="The Agent Run waiting for Human Approval."),
        state_dir: Path | None = typer.Option(None, "--state-dir", file_okay=False),
        model: str | None = typer.Option(None, "--model", envvar="REPOPILOT_MODEL"),
        api_key: str | None = typer.Option(None, "--api-key", envvar="REPOPILOT_API_KEY", show_default=False),
        base_url: str | None = typer.Option(None, "--base-url", envvar="REPOPILOT_BASE_URL"),
    ) -> None:
        """Approve the persisted high-risk Tool Call, then resume the Agent Run."""

        _resume(run_id, state_dir, model, api_key, base_url, approval_granted=True)

    @app.command()
    def reject(
        run_id: str = typer.Argument(..., help="The Agent Run waiting for Human Approval."),
        state_dir: Path | None = typer.Option(None, "--state-dir", file_okay=False),
        model: str | None = typer.Option(None, "--model", envvar="REPOPILOT_MODEL"),
        api_key: str | None = typer.Option(None, "--api-key", envvar="REPOPILOT_API_KEY", show_default=False),
        base_url: str | None = typer.Option(None, "--base-url", envvar="REPOPILOT_BASE_URL"),
    ) -> None:
        """Reject the persisted high-risk Tool Call and let the model revise its plan."""

        _resume(run_id, state_dir, model, api_key, base_url, approval_granted=False)

    return app


def _create_litellm_model(options: ModelOptions) -> ToolCallingModel:
    if not options.model_name:
        raise ValueError("Provide --model or set REPOPILOT_MODEL.")
    return LiteLLMToolCallingModel(
        model_name=options.model_name,
        api_key=options.api_key,
        base_url=options.base_url,
    )


def _credential_values(api_key: str | None) -> list[str]:
    values = [api_key] if api_key else []
    for name, value in os.environ.items():
        if any(marker in name.upper() for marker in ("KEY", "TOKEN", "SECRET", "PASSWORD")):
            values.append(value)
    return values


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
