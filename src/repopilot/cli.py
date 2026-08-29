"""RepoPilot's CLI entry point for a first Local Agent Run."""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import typer
from platformdirs import user_state_dir

from repopilot.artifacts import RunArtifacts
from repopilot.environment import LocalExecutionEnvironment
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


def create_app(model_factory: ModelFactory | None = None) -> typer.Typer:
    """Build the CLI, allowing Runtime Tests to replace only the model boundary."""

    app = typer.Typer(add_completion=False, help="Run RepoPilot against a local Target Repository.")
    factory = model_factory or _create_litellm_model

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
    ) -> None:
        if task is None:
            task = typer.prompt("Task")
        typer.echo("Warning: Local Environment executes commands directly in the Target Repository.")
        options = ModelOptions(model_name=model, api_key=api_key, base_url=base_url)
        try:
            tool_calling_model = factory(options)
        except ValueError as error:
            raise typer.BadParameter(str(error), param_hint="--model") from error
        secret_values = _credential_values(api_key)
        artifacts = RunArtifacts(state_dir or Path(user_state_dir("repopilot")) / "runs", secrets=secret_values)
        environment = LocalExecutionEnvironment(repository)
        plan_history = PlanHistory.for_task(task)
        try:
            result = AgentRuntime(
                tool_calling_model,
                create_tool_registry(environment, repository, plan_history),
                artifacts,
                plan_history,
            ).run(task, repository)
        finally:
            environment.close()
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
