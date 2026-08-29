"""RepoPilot's CLI entry point for a repository-scoped Agent Run."""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import typer
from platformdirs import user_state_dir

from repopilot.artifacts import RunArtifacts
from repopilot.environment import (
    EnvironmentCreationError,
    EnvironmentRequest,
    ExecutionEnvironmentFactory,
    create_execution_environment,
    validate_environment_request,
)
from repopilot.model import LiteLLMToolCallingModel, ToolCallingModel
from repopilot.plan import PlanHistory
from repopilot.runtime import AgentRuntime
from repopilot.tools import create_tool_registry


@dataclass(frozen=True)
class ModelOptions:
    model_name: str | None
    api_key: str | None
    base_url: str | None


ModelFactory = Callable[[ModelOptions], ToolCallingModel]


class EnvironmentOption(str, Enum):
    """Execution Environment choices exposed by the product CLI."""

    LOCAL = "local"
    DOCKER = "docker"


def create_app(
    model_factory: ModelFactory | None = None,
    environment_factory: ExecutionEnvironmentFactory | None = None,
) -> typer.Typer:
    """Build the CLI, allowing Runtime Tests to replace composition boundaries."""

    app = typer.Typer(add_completion=False, help="Run RepoPilot against a Target Repository.")
    selected_model_factory = model_factory or _create_litellm_model
    selected_environment_factory = environment_factory or create_execution_environment

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
    ) -> None:
        if task is None:
            task = typer.prompt("Task")
        request = EnvironmentRequest(target_repository=repository, environment=environment_name.value, image=image)
        try:
            validate_environment_request(request)
        except ValueError as error:
            parameter = "--image" if environment_name is EnvironmentOption.DOCKER and not image else "--environment"
            raise typer.BadParameter(str(error), param_hint=parameter) from error
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
        try:
            result = AgentRuntime(
                tool_calling_model,
                create_tool_registry(execution_environment, repository, plan_history),
                artifacts,
                plan_history,
            ).run(task, repository)
        finally:
            execution_environment.close()
        typer.echo(f"Agent Run {result.run_id}: {result.status}")
        typer.echo(f"Plan v{result.plan.version}")
        for step in result.plan.steps:
            typer.echo(f"- [{step.status.value}] {step.description}")
        typer.echo(f"Artifacts: {result.artifact_directory}")

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


app = create_app()
