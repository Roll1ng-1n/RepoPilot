"""Repository Tool schemas, validation, and Environment-backed dispatch."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from repopilot.environment import Command, ExecutionEnvironment
from repopilot.model import ToolCall


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


class FinishTaskArguments(_ToolArguments):
    summary: str = Field(min_length=1)


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
        except ValueError as error:
            return {"ok": False, "error": "invalid_repository_path", "details": str(error)}


def create_tool_registry(environment: ExecutionEnvironment, target_repository: Path) -> ToolRegistry:
    """Create the first vertical slice of read-only tools plus terminal Agent Control."""

    root = target_repository.resolve()

    def safe_path(path: str) -> str:
        resolved = (root / path).resolve()
        try:
            relative = resolved.relative_to(root)
        except ValueError as error:
            raise ValueError(f"Path must remain inside the Target Repository: {path}") from error
        return str(relative) or "."

    def execute(command: Command) -> dict[str, Any]:
        return environment.execute(command).to_dict()

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

    def finish_task(arguments: _ToolArguments) -> dict[str, Any]:
        return {"status": "UNVERIFIED", "summary": arguments.summary}  # type: ignore[attr-defined]

    return ToolRegistry(
        [
            _ToolDefinition("list_files", "List files below a repository path.", ListFilesArguments, list_files),
            _ToolDefinition(
                "search_code", "Search repository code for literal text.", SearchCodeArguments, search_code
            ),
            _ToolDefinition("read_file", "Read a bounded range of a repository file.", ReadFileArguments, read_file),
            _ToolDefinition("run_command", "Run a command in the Target Repository.", RunCommandArguments, run_command),
            _ToolDefinition(
                "finish_task", "Finish the Agent Run with an unverified summary.", FinishTaskArguments, finish_task
            ),
        ]
    )
