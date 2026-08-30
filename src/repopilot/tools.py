"""Repository Tool schemas, validation, and Environment-backed dispatch."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from repopilot.environment import Command, ExecutionEnvironment
from repopilot.model import ToolCall
from repopilot.plan import PlanHistory, PlanInvariantError, PlanStep, PlanStepStatus


class _ToolArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ListFilesArguments(_ToolArguments):
    path: str = "."


class SearchCodeArguments(_ToolArguments):
    query: str = Field(min_length=1)
    path: str = "."
    max_results: int = Field(default=50, ge=1, le=500)


class ReadFileArguments(_ToolArguments):
    path: str = Field(min_length=1)
    start_line: int = Field(default=1, ge=1)
    max_lines: int = Field(default=200, ge=1, le=2_000)


class RunCommandArguments(_ToolArguments):
    command: str = Field(min_length=1)


class ApplyPatchArguments(_ToolArguments):
    patch: str = Field(min_length=1)


class ViewDiffArguments(_ToolArguments):
    pass


class VerifyTaskArguments(_ToolArguments):
    command: str = Field(min_length=1)
    scope: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class FinishTaskArguments(_ToolArguments):
    root_cause: str = Field(min_length=1)
    changes: list[str] = Field(min_length=1)
    risks: list[str] = Field(default_factory=list)


class UpdatePlanArguments(_ToolArguments):
    step_id: str = Field(min_length=1)
    status: PlanStepStatus


class ReplanStepArguments(_ToolArguments):
    id: str = Field(min_length=1)
    description: str = Field(min_length=1)
    completion_condition: str = Field(min_length=1)


class ReplanArguments(_ToolArguments):
    reason: str = Field(min_length=1)
    steps: list[ReplanStepArguments] = Field(min_length=1)


@dataclass(frozen=True)
class _ToolDefinition:
    name: str
    description: str
    arguments_type: type[_ToolArguments]
    handler: Callable[[_ToolArguments], dict[str, Any]]

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.arguments_type.model_json_schema(),
            },
        }


class ToolRegistry:
    """The Runtime's only route to repository capabilities."""

    def __init__(self, definitions: list[_ToolDefinition]):
        self._definitions = {definition.name: definition for definition in definitions}

    @property
    def schemas(self) -> list[dict[str, Any]]:
        return [definition.schema() for definition in self._definitions.values()]

    def dispatch(self, tool_call: ToolCall) -> dict[str, Any]:
        definition = self._definitions.get(tool_call.name)
        if definition is None:
            return {"ok": False, "error": "unknown_tool", "tool_name": tool_call.name}
        try:
            arguments = definition.arguments_type.model_validate(tool_call.arguments)
        except ValidationError as error:
            return {"ok": False, "error": "invalid_tool_arguments", "details": error.errors()}
        try:
            return {"ok": True, "result": definition.handler(arguments)}
        except PlanInvariantError as error:
            return {"ok": False, "error": "invalid_plan", "details": str(error)}
        except ValueError as error:
            return {"ok": False, "error": "invalid_repository_path", "details": str(error)}
        except (OSError, TimeoutError) as error:
            return {"ok": False, "error": "environment_error", "details": str(error)}


def create_tool_registry(
    environment: ExecutionEnvironment,
    target_repository: Path,
    plan_history: PlanHistory,
    *,
    command_timeout_seconds: float = 300.0,
    verifications: list[dict[str, Any]] | None = None,
) -> ToolRegistry:
    """Create repository and Agent Control Tools without exposing the Environment to the Runtime."""

    root = target_repository.resolve()
    verifications = verifications if verifications is not None else []

    def safe_path(path: str) -> str:
        resolved = (root / path).resolve()
        try:
            relative = resolved.relative_to(root)
        except ValueError as error:
            raise ValueError(f"Path must remain inside the Target Repository: {path}") from error
        return str(relative) or "."

    def execute(command: Command) -> dict[str, Any]:
        return environment.execute(replace(command, timeout_seconds=command_timeout_seconds)).to_dict()

    def current_diff() -> dict[str, Any]:
        return execute(
            Command(
                (
                    "bash",
                    "-lc",
                    "git diff --no-ext-diff --binary --; "
                    "git ls-files --others --exclude-standard -z | "
                    "xargs -0 -r -n1 sh -c 'git diff --no-index --binary /dev/null \"$0\" || true'",
                )
            )
        )

    def list_files(arguments: _ToolArguments) -> dict[str, Any]:
        path = safe_path(arguments.path)  # type: ignore[attr-defined]
        return execute(Command(("find", path, "-type", "f", "-not", "-path", "*/.git/*")))

    def search_code(arguments: _ToolArguments) -> dict[str, Any]:
        path = safe_path(arguments.path)  # type: ignore[attr-defined]
        return execute(
            Command(
                (
                    "rg",
                    "--line-number",
                    "--no-heading",
                    "--fixed-strings",
                    "--max-count",
                    str(arguments.max_results),  # type: ignore[attr-defined]
                    arguments.query,  # type: ignore[attr-defined]
                    path,
                )
            )
        )

    def read_file(arguments: _ToolArguments) -> dict[str, Any]:
        path = safe_path(arguments.path)  # type: ignore[attr-defined]
        last_line = arguments.start_line + arguments.max_lines - 1  # type: ignore[attr-defined]
        return execute(Command(("sed", "-n", f"{arguments.start_line},{last_line}p", path)))  # type: ignore[attr-defined]

    def run_command(arguments: _ToolArguments) -> dict[str, Any]:
        return execute(Command(("bash", "-lc", arguments.command)))  # type: ignore[attr-defined]

    def apply_patch(arguments: _ToolArguments) -> dict[str, Any]:
        result = execute(
            Command(
                ("git", "apply", "--whitespace=nowarn", "-"),
                stdin=arguments.patch,  # type: ignore[attr-defined]
            )
        )
        return {"applied": result["exit_code"] == 0, "result": result}

    def view_diff(_arguments: _ToolArguments) -> dict[str, Any]:
        result = current_diff()
        return {"patch": result["stdout"], "result": result}

    def verify_task(arguments: _ToolArguments) -> dict[str, Any]:
        result = execute(Command(("bash", "-lc", arguments.command)))  # type: ignore[attr-defined]
        verification = {
            "command": arguments.command,  # type: ignore[attr-defined]
            "scope": arguments.scope,  # type: ignore[attr-defined]
            "reason": arguments.reason,  # type: ignore[attr-defined]
            "result": result,
        }
        verifications.append(verification)
        return verification

    def finish_task(arguments: _ToolArguments) -> dict[str, Any]:
        diff = current_diff()
        status = "SUCCEEDED" if any(item["result"]["exit_code"] == 0 for item in verifications) else "UNVERIFIED"
        return {
            "status": status,
            "final_patch": diff["stdout"],
            "verifications": verifications,
            "report": {
                "root_cause": arguments.root_cause,  # type: ignore[attr-defined]
                "changes": arguments.changes,  # type: ignore[attr-defined]
                "risks": arguments.risks,  # type: ignore[attr-defined]
            },
        }

    def update_plan(arguments: _ToolArguments) -> dict[str, Any]:
        updated = plan_history.update_step(arguments.step_id, arguments.status)  # type: ignore[attr-defined]
        return {"plan": updated.to_dict()}

    def replan(arguments: _ToolArguments) -> dict[str, Any]:
        replacement_steps = [
            PlanStep(step.id, step.description, step.completion_condition)
            for step in arguments.steps  # type: ignore[attr-defined]
        ]
        updated = plan_history.replan(replacement_steps, arguments.reason)  # type: ignore[attr-defined]
        return {"plan": updated.to_dict(), "reason": arguments.reason}  # type: ignore[attr-defined]

    return ToolRegistry(
        [
            _ToolDefinition("list_files", "List files below a repository path.", ListFilesArguments, list_files),
            _ToolDefinition(
                "search_code", "Search repository code for literal text.", SearchCodeArguments, search_code
            ),
            _ToolDefinition("read_file", "Read a bounded range of a repository file.", ReadFileArguments, read_file),
            _ToolDefinition("run_command", "Run a command in the Target Repository.", RunCommandArguments, run_command),
            _ToolDefinition(
                "apply_patch", "Apply a unified diff patch to the Target Repository.", ApplyPatchArguments, apply_patch
            ),
            _ToolDefinition(
                "view_diff", "Show the current uncommitted Target Repository diff.", ViewDiffArguments, view_diff
            ),
            _ToolDefinition(
                "verify_task",
                "Run an executable Task Verification with its scope and reason.",
                VerifyTaskArguments,
                verify_task,
            ),
            _ToolDefinition(
                "finish_task",
                "Finish the Agent Run with its root cause, changes, and risks.",
                FinishTaskArguments,
                finish_task,
            ),
            _ToolDefinition("update_plan", "Update the status of one Plan Step.", UpdatePlanArguments, update_plan),
            _ToolDefinition(
                "replan", "Replace unfinished Plan Steps while preserving completed work.", ReplanArguments, replan
            ),
        ]
    )
