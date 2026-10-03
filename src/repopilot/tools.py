"""Repository Tool schemas, validation, and Environment-backed dispatch."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from repopilot.approval import ToolCallSnapshot
from repopilot.budget import RunBudgetTracker
from repopilot.checkpoint import capture_repository_state
from repopilot.environment import Command, ExecutionEnvironment
from repopilot.model import ToolCall
from repopilot.patches import PatchFormatError, normalize_patch
from repopilot.plan import PlanHistory, PlanInvariantError, PlanStep, PlanStepStatus
from repopilot.profile import applicable_instructions
from repopilot.verification_gate import VerificationGate


class _ToolArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ListFilesArguments(_ToolArguments):
    path: str = "."
    offset: int = Field(default=0, ge=0)
    max_results: int = Field(default=200, ge=1, le=500)


class SearchCodeArguments(_ToolArguments):
    query: str = Field(min_length=1)
    path: str = "."
    max_results: int = Field(default=50, ge=1, le=500)
    offset: int = Field(default=0, ge=0)


class ReadArtifactArguments(_ToolArguments):
    artifact: str
    offset: int = Field(default=0, ge=0)
    max_characters: int = Field(default=8000, ge=1, le=16000)


class ReadFileArguments(_ToolArguments):
    path: str = Field(min_length=1)
    start_line: int = Field(default=1, ge=1)
    max_lines: int = Field(default=200, ge=1, le=2_000)


class RunCommandArguments(_ToolArguments):
    command: str = Field(min_length=1)


class ApplyPatchArguments(_ToolArguments):
    patch: str = Field(
        min_length=1,
        description="Git unified diff, or *** Begin Patch with Add/Update/Delete File blocks and @@ hunks.",
    )


class GitCommitArguments(_ToolArguments):
    message: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    paths: list[Annotated[str, Field(min_length=1)]] = Field(min_length=1)


class ViewDiffArguments(_ToolArguments):
    pass


class TaskVerificationArguments(_ToolArguments):
    command: str = Field(min_length=1)
    scope: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    check_id: str | None = Field(
        default=None, min_length=1, description="Stable check identity; reuse when command or scope changes."
    )
    supersedes: list[int] = Field(
        default_factory=list,
        description="Prior verification sequence numbers replaced by this check. Required commands remain mandatory.",
    )


class VerifyTaskArguments(TaskVerificationArguments):
    step_ids: list[str] = Field(default_factory=list)


class FinishTaskArguments(_ToolArguments):
    root_cause: str = Field(min_length=1)
    changes: list[str] = Field(min_length=1)
    rationale: str | None = None
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


class RecordFactArguments(_ToolArguments):
    fact: str = Field(min_length=1, pattern=r".*\S.*")


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


@dataclass(frozen=True)
class PreparedToolCall:
    """A validated Tool Call ready for risk review and eventual execution."""

    tool_call: ToolCall
    snapshot: ToolCallSnapshot
    _arguments: _ToolArguments
    _handler: Callable[[_ToolArguments], dict[str, Any]]


class ToolRegistry:
    """The Runtime's only route to repository capabilities."""

    def __init__(self, definitions: list[_ToolDefinition]):
        self._definitions = {definition.name: definition for definition in definitions}
        self.budget: RunBudgetTracker | None = None
        self.completion_decision: dict[str, Any] = {}
        self.artifacts = None
        self.instruction_observer = None
        self.root = None
        self.planning_enabled = True
        self.plan_history = None

    def store_output(self, value):
        if self.artifacts is None:
            return None
        serialized = json.dumps(value, sort_keys=True, ensure_ascii=True)
        name = "tool-output-" + hashlib.sha256(serialized.encode()).hexdigest() + ".json"
        self.artifacts.write_text(name, serialized)
        return name

    def model_observation(self, value):
        serialized = json.dumps(value, sort_keys=True)
        if len(serialized) <= 12000:
            return value
        artifact = self.store_output(value)
        return {
            "ok": value.get("ok"),
            "truncated": True,
            "artifact": artifact,
            "preview": serialized[:10000],
            "characters": len(serialized),
        }

    @property
    def schemas(self) -> list[dict[str, Any]]:
        return [definition.schema() for definition in self._definitions.values()]

    def prepare(self, tool_call: ToolCall) -> PreparedToolCall | dict[str, Any]:
        """Validate a Tool Call without causing repository side effects."""

        if tool_call.protocol_error:
            return {"ok": False, "error": "invalid_tool_arguments", "details": tool_call.protocol_error}
        definition = self._definitions.get(tool_call.name)
        if definition is None:
            return {"ok": False, "error": "unknown_tool", "tool_name": tool_call.name}
        try:
            arguments = definition.arguments_type.model_validate(tool_call.arguments)
        except ValidationError as error:
            return {"ok": False, "error": "invalid_tool_arguments", "details": error.errors()}
        if tool_call.name == "apply_patch" and self.root is not None:
            try:
                arguments.patch = normalize_patch(arguments.patch, self.root)
            except (PatchFormatError, UnicodeError) as error:
                return {"ok": False, "error": "invalid_patch", "details": str(error)}
        if tool_call.name == "replan" and self.plan_history is not None:
            try:
                self.plan_history.current.replan(
                    [PlanStep(step.id, step.description, step.completion_condition) for step in arguments.steps],
                    arguments.reason,
                )
            except PlanInvariantError as error:
                return {"ok": False, "error": "invalid_plan", "details": str(error)}
        if self.instruction_observer is not None and self.root is not None:
            paths = [getattr(arguments, "path", ".")]
            if tool_call.name == "apply_patch":
                paths = [
                    line[4:].split("\t")[0]
                    for line in arguments.patch.splitlines()
                    if line.startswith(("--- ", "+++ ")) and line[4:] != "/dev/null"
                ]
                paths = [p[2:] if p.startswith(("a/", "b/")) else p for p in paths]
            discovered = []
            try:
                for path in paths:
                    for instruction in applicable_instructions(self.root, path):
                        if self.instruction_observer(instruction):
                            discovered.append(instruction)
            except ValueError as error:
                return {"ok": False, "error": "invalid_repository_path", "details": str(error)}
            if discovered and tool_call.name == "apply_patch":
                return {
                    "ok": False,
                    "error": "repository_instructions_discovered",
                    "instructions": discovered,
                    "details": "Review scoped instructions before resubmitting this write.",
                }
        normalized_call = ToolCall(tool_call.id, tool_call.name, arguments.model_dump(mode="json"))
        return PreparedToolCall(
            tool_call=normalized_call,
            snapshot=ToolCallSnapshot.from_tool_call(normalized_call),
            _arguments=arguments,
            _handler=definition.handler,
        )

    def execute(self, prepared: PreparedToolCall) -> dict[str, Any]:
        """Execute a previously validated Tool Call exactly once."""

        try:
            return {"ok": True, "result": prepared._handler(prepared._arguments)}
        except PlanInvariantError as error:
            return {"ok": False, "error": "invalid_plan", "details": str(error)}
        except ValueError as error:
            return {"ok": False, "error": "invalid_repository_path", "details": str(error)}
        except (OSError, TimeoutError) as error:
            return {"ok": False, "error": "environment_error", "details": str(error)}

    def dispatch(self, tool_call: ToolCall) -> dict[str, Any]:
        """Backward-compatible prepare-and-execute dispatch for callers without approval."""

        prepared = self.prepare(tool_call)
        if isinstance(prepared, dict):
            return prepared
        return self.execute(prepared)

    def capture_diff(self) -> dict[str, Any]:
        """Capture the current repository patch through the read-only Diff Tool."""

        prepared = self.prepare(ToolCall("artifact-diff", "view_diff", {}))
        if isinstance(prepared, dict):
            return prepared
        return self.execute(prepared)


def create_tool_registry(
    environment: ExecutionEnvironment,
    target_repository: Path,
    plan_history: PlanHistory,
    *,
    command_timeout_seconds: float = 300.0,
    verifications: list[dict[str, Any]] | None = None,
    required_verifications: tuple[str, ...] = (),
    planning_enabled: bool = True,
) -> ToolRegistry:
    """Create repository and Agent Control Tools without exposing the Environment to the Runtime."""

    root = target_repository.resolve()
    verifications = verifications if verifications is not None else []
    gate = VerificationGate(verifications, plan_history, required_verifications)

    def safe_path(path: str) -> str:
        resolved = (root / path).resolve()
        try:
            relative = resolved.relative_to(root)
        except ValueError as error:
            raise ValueError(f"Path must remain inside the Target Repository: {path}") from error
        return str(relative) or "."

    def execute(command: Command) -> dict[str, Any]:
        timeout = command_timeout_seconds
        if registry.budget is not None:
            timeout = min(timeout, registry.budget.remaining_seconds())
        result = environment.execute(
            replace(command, timeout_seconds=timeout, full_output=command.full_output or registry.artifacts is not None)
        ).to_dict()
        if registry.budget is not None:
            registry.budget.remaining_seconds()
        return result

    def current_diff() -> dict[str, Any]:
        return execute(
            Command(
                (
                    "bash",
                    "-lc",
                    "git diff --no-ext-diff --binary HEAD --; "
                    "git ls-files --others --exclude-standard -z | "
                    "xargs -0 -r -n1 sh -c 'git diff --no-index --binary /dev/null \"$0\" || true'",
                ),
                full_output=True,
            )
        )

    def list_files(arguments: _ToolArguments) -> dict[str, Any]:
        path = safe_path(arguments.path)  # type: ignore[attr-defined]
        result = execute(
            Command(("git", "ls-files", "--cached", "--others", "--exclude-standard", "--", path), full_output=True)
        )
        lines = sorted(set(result["stdout"].splitlines()))
        offset = arguments.offset  # type: ignore[attr-defined]
        limit = arguments.max_results  # type: ignore[attr-defined]
        result["stdout"] = "\n".join(lines[offset : offset + limit])
        result["next_offset"] = offset + limit if offset + limit < len(lines) else None
        result["total_results"] = len(lines)
        return result

    def search_code(arguments: _ToolArguments) -> dict[str, Any]:
        path = safe_path(arguments.path)  # type: ignore[attr-defined]
        result = execute(
            Command(
                (
                    "rg",
                    "--line-number",
                    "--no-heading",
                    "--fixed-strings",
                    "--",
                    arguments.query,  # type: ignore[attr-defined]
                    path,
                ),
                full_output=True,
            )
        )
        lines = result["stdout"].splitlines()
        limit = arguments.max_results  # type: ignore[attr-defined]
        offset = arguments.offset
        result["artifact"] = registry.store_output(result)
        result["stdout"] = "\n".join(lines[offset : offset + limit])
        result["next_offset"] = offset + limit if offset + limit < len(lines) else None
        result["truncated"] = result["truncated"] or len(lines) > limit
        return result

    def read_artifact(arguments):
        if registry.artifacts is None or not re.fullmatch(r"tool-output-[0-9a-f]{64}\.json", arguments.artifact):
            raise ValueError("Unknown artifact reference.")
        text = (registry.artifacts.path / arguments.artifact).read_text()
        end = arguments.offset + arguments.max_characters
        return {"content": text[arguments.offset : end], "next_offset": end if end < len(text) else None}

    def read_file(arguments: _ToolArguments) -> dict[str, Any]:
        path = safe_path(arguments.path)  # type: ignore[attr-defined]
        last_line = arguments.start_line + arguments.max_lines - 1  # type: ignore[attr-defined]
        result = execute(Command(("sed", "-n", f"{arguments.start_line},{last_line}p", path)))
        result["repository_instructions"] = applicable_instructions(root, path)
        return result  # type: ignore[attr-defined]

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

    def git_commit(arguments: _ToolArguments) -> dict[str, Any]:
        paths = [safe_path(path) for path in arguments.paths]  # type: ignore[attr-defined]
        patch = current_diff()
        stage = execute(Command(("git", "add", "--", *paths)))
        if stage["exit_code"] != 0:
            return {
                "committed": False,
                "message": arguments.message,  # type: ignore[attr-defined]
                "reason": arguments.reason,  # type: ignore[attr-defined]
                "paths": paths,
                "patch": patch["stdout"],
                "stage": stage,
            }
        commit = execute(Command(("git", "commit", "--message", arguments.message, "--", *paths)))  # type: ignore[attr-defined]
        if commit["exit_code"] != 0:
            return {
                "committed": False,
                "message": arguments.message,  # type: ignore[attr-defined]
                "reason": arguments.reason,  # type: ignore[attr-defined]
                "paths": paths,
                "patch": patch["stdout"],
                "stage": stage,
                "result": commit,
            }
        revision = execute(Command(("git", "rev-parse", "HEAD")))
        return {
            "committed": revision["exit_code"] == 0,
            "message": arguments.message,  # type: ignore[attr-defined]
            "reason": arguments.reason,  # type: ignore[attr-defined]
            "paths": paths,
            "patch": patch["stdout"],
            "commit_hash": revision["stdout"].strip() if revision["exit_code"] == 0 else None,
            "stage": stage,
            "result": commit,
            "revision": revision,
        }

    def view_diff(_arguments: _ToolArguments) -> dict[str, Any]:
        result = current_diff()
        return {"patch": result["stdout"], "result": result}

    def verify_task(arguments: _ToolArguments) -> dict[str, Any]:
        check_id, previous, step_ids = gate.prepare(arguments)
        before = capture_repository_state(root, verification=True)["diff_fingerprint"]
        result = execute(Command(("bash", "-lc", arguments.command)))  # type: ignore[attr-defined]
        verification = {
            "sequence": len(verifications) + 1,
            "check_id": check_id,
            "explicit_check_id": arguments.check_id is not None or bool(previous and previous.get("explicit_check_id")),
            "supersedes": arguments.supersedes,
            "plan_step_ids": step_ids,
            "before_fingerprint": before,
            "after_fingerprint": capture_repository_state(root, verification=True)["diff_fingerprint"],
            "command": arguments.command,  # type: ignore[attr-defined]
            "scope": arguments.scope,  # type: ignore[attr-defined]
            "reason": arguments.reason,  # type: ignore[attr-defined]
            "result": result,
        }
        verifications.append(verification)
        return verification

    def finish_task(arguments: _ToolArguments) -> dict[str, Any]:
        diff = current_diff()
        fingerprint = capture_repository_state(root, verification=True)["diff_fingerprint"]
        registry.completion_decision = gate.evaluate(fingerprint)
        problems = registry.completion_decision["problems"]
        if problems:
            return {
                "status": "INCOMPLETE",
                **registry.completion_decision,
                "retry_hint": "Rerun each listed check with its check_id. To replace an obsolete check, pass its sequence in supersedes. Required commands must still pass on the final source state.",
            }
        status = "SUCCEEDED" if verifications else "UNVERIFIED"
        return {
            "status": status,
            "completion_allowed": True,
            "evidence_scope": "required_commands" if required_verifications else "model_selected_checks",
            "required_verifications": list(required_verifications),
            "final_patch": diff["stdout"],
            "verifications": verifications,
            "report": {
                "root_cause": arguments.root_cause,  # type: ignore[attr-defined]
                "changes": arguments.changes,  # type: ignore[attr-defined]
                "rationale": arguments.rationale,  # type: ignore[attr-defined]
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

    def record_fact(arguments: _ToolArguments) -> dict[str, Any]:
        return {"fact": arguments.fact.strip()}  # type: ignore[attr-defined]

    registry = ToolRegistry(
        [
            _ToolDefinition(
                "read_artifact",
                "Read the next character range of a complete tool output artifact.",
                ReadArtifactArguments,
                read_artifact,
            ),
            _ToolDefinition("list_files", "List files below a repository path.", ListFilesArguments, list_files),
            _ToolDefinition(
                "search_code", "Search repository code for literal text.", SearchCodeArguments, search_code
            ),
            _ToolDefinition("read_file", "Read a bounded range of a repository file.", ReadFileArguments, read_file),
            _ToolDefinition("run_command", "Run a command in the Target Repository.", RunCommandArguments, run_command),
            _ToolDefinition(
                "apply_patch",
                "Apply a Git unified diff or *** Begin Patch Add/Update/Delete blocks. Include exact, unique context in @@ hunks.",
                ApplyPatchArguments,
                apply_patch,
            ),
            _ToolDefinition(
                "git_commit",
                "Create a local Git Commit for explicit repository paths after Human Approval.",
                GitCommitArguments,
                git_commit,
            ),
            _ToolDefinition(
                "view_diff", "Show the current uncommitted Target Repository diff.", ViewDiffArguments, view_diff
            ),
            _ToolDefinition(
                "verify_task",
                "Run an executable Task Verification with its scope and reason.",
                VerifyTaskArguments if planning_enabled else TaskVerificationArguments,
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
            _ToolDefinition(
                "record_fact",
                "Record an important fact that must remain in future model context.",
                RecordFactArguments,
                record_fact,
            ),
        ]
    )
    registry.verifications = verifications
    registry.verification_gate = gate
    registry.root = root
    registry.plan_history = plan_history
    registry.planning_enabled = planning_enabled
    if not planning_enabled:
        for name in ("update_plan", "replan"):
            registry._definitions.pop(name)
    return registry
