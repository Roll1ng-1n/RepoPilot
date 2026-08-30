"""Human Approval policy and durable pending-approval data."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any

from repopilot.model import ToolCall


class RiskDecision(str, Enum):
    """The action RepoPilot must take before executing a prepared Tool Call."""

    ALLOW = "ALLOW"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"
    DENY = "DENY"


@dataclass(frozen=True)
class RiskAssessment:
    """A decision together with the user-facing reason that produced it."""

    decision: RiskDecision
    reason: str


@dataclass(frozen=True)
class ToolCallSnapshot:
    """An immutable, JSON-stable record of a Tool Call awaiting approval."""

    id: str
    name: str
    _arguments_json: str

    @classmethod
    def from_tool_call(cls, tool_call: ToolCall) -> ToolCallSnapshot:
        arguments_json = json.dumps(tool_call.arguments, sort_keys=True, separators=(",", ":"))
        return cls(tool_call.id, tool_call.name, arguments_json)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> ToolCallSnapshot:
        identifier = value.get("id")
        name = value.get("name")
        arguments = value.get("arguments")
        if not isinstance(identifier, str) or not identifier:
            raise ValueError("Approval Request has an invalid Tool Call ID.")
        if not isinstance(name, str) or not name:
            raise ValueError("Approval Request has an invalid Tool Call name.")
        if not isinstance(arguments, dict):
            raise ValueError("Approval Request has invalid Tool Call arguments.")
        return cls.from_tool_call(ToolCall(identifier, name, arguments))

    @property
    def arguments(self) -> dict[str, Any]:
        value = json.loads(self._arguments_json)
        assert isinstance(value, dict)
        return value

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "name": self.name, "arguments": self.arguments}

    def to_tool_call(self) -> ToolCall:
        return ToolCall(self.id, self.name, self.arguments)


@dataclass(frozen=True)
class ApprovalRequest:
    """The durable user decision requested for one high-risk Tool Call."""

    tool_call: ToolCallSnapshot
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {"tool_call": self.tool_call.to_dict(), "reason": self.reason}

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> ApprovalRequest:
        tool_call = value.get("tool_call")
        reason = value.get("reason")
        if not isinstance(tool_call, dict) or not isinstance(reason, str) or not reason:
            raise ValueError("Checkpoint has an invalid Approval Request.")
        return cls(ToolCallSnapshot.from_dict(tool_call), reason)


@dataclass(frozen=True)
class ApprovalContext:
    """Explicit execution context used only for the bounded auto-approval exception."""

    environment: str
    disposable_benchmark: bool = False
    automatic_approval: bool = False

    @property
    def permits_automatic_approval(self) -> bool:
        """Only an explicitly disposable Docker benchmark may auto-approve."""

        return self.environment == "docker" and self.disposable_benchmark and self.automatic_approval

    def to_dict(self) -> dict[str, object]:
        return {
            "environment": self.environment,
            "disposable_benchmark": self.disposable_benchmark,
            "automatic_approval": self.automatic_approval,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> ApprovalContext:
        environment = value.get("environment")
        disposable_benchmark = value.get("disposable_benchmark", False)
        automatic_approval = value.get("automatic_approval", False)
        if (
            not isinstance(environment, str)
            or not isinstance(disposable_benchmark, bool)
            or not isinstance(automatic_approval, bool)
        ):
            raise ValueError("Checkpoint has an invalid Approval Context.")
        return cls(environment, disposable_benchmark, automatic_approval)


class ApprovalPolicy:
    """Best-effort V1 risk classification for prepared repository operations.

    This is intentionally a small recognizer, not a shell parser or security
    boundary. It identifies the destructive, dependency-installing, and Git
    writing cases that should interrupt an Agent Run for Human Approval.
    """

    _FORBIDDEN_GIT = re.compile(r"\bgit\b[^;&|\n]*(?:\bpush\b|\brebase\b|\breset\b)", re.IGNORECASE)
    _FORBIDDEN_PULL_REQUEST = re.compile(r"\b(?:gh|hub)\s+(?:pr|pull-request)\s+(?:create|merge)\b", re.IGNORECASE)
    _DELETION = re.compile(r"\b(?:rm|rmdir|unlink)\b|\bfind\b[^;&|\n]*\s-delete\b", re.IGNORECASE)
    _DEPENDENCY_INSTALL = re.compile(
        r"\b(?:pip(?:3)?|npm|yarn|pnpm|poetry|uv|apt(?:-get)?|brew)\s+(?:install|add|sync|ci)\b",
        re.IGNORECASE,
    )
    _GIT_WRITE = re.compile(
        r"\bgit\b[^;&|\n]*\b(?:add|am|apply|branch|checkout|cherry-pick|clean|commit|config|fetch|merge|mv|pull|restore|rm|stash|switch|tag)\b",
        re.IGNORECASE,
    )
    _COMMAND_TOOLS = {"run_command", "verify_task"}

    def __init__(self, context: ApprovalContext):
        self._context = context

    def assess(self, tool_call: ToolCallSnapshot) -> RiskAssessment:
        """Classify one validated Tool Call without executing it."""

        permanent_denial = self._permanent_denial(tool_call)
        if permanent_denial is not None:
            return RiskAssessment(RiskDecision.DENY, permanent_denial)
        approval_reason = self._approval_reason(tool_call)
        if approval_reason is None:
            return RiskAssessment(RiskDecision.ALLOW, "Routine repository operation.")
        if self._context.permits_automatic_approval:
            return RiskAssessment(
                RiskDecision.ALLOW,
                f"Automatically approved in the explicit disposable Docker benchmark context: {approval_reason}",
            )
        return RiskAssessment(RiskDecision.REQUIRE_APPROVAL, approval_reason)

    @classmethod
    def _permanent_denial(cls, tool_call: ToolCallSnapshot) -> str | None:
        if tool_call.name not in cls._COMMAND_TOOLS:
            return None
        command = tool_call.arguments.get("command")
        if not isinstance(command, str):
            return None
        if cls._FORBIDDEN_GIT.search(command):
            return "Git push, rebase, and reset are permanently unsupported by RepoPilot V1."
        if cls._FORBIDDEN_PULL_REQUEST.search(command):
            return "Pull Request creation and merging are permanently unsupported by RepoPilot V1."
        return None

    @classmethod
    def _approval_reason(cls, tool_call: ToolCallSnapshot) -> str | None:
        if tool_call.name == "git_commit":
            return "Creating a local Git Commit writes Target Repository history."
        if tool_call.name == "apply_patch":
            patch = tool_call.arguments.get("patch")
            if isinstance(patch, str) and "deleted file mode" in patch.lower():
                return "The patch deletes a Target Repository file."
            return None
        if tool_call.name not in cls._COMMAND_TOOLS:
            return None
        command = tool_call.arguments.get("command")
        if not isinstance(command, str):
            return None
        if cls._DELETION.search(command):
            return "The command may delete Target Repository files."
        if cls._DEPENDENCY_INSTALL.search(command):
            return "The command installs or changes dependencies."
        if cls._GIT_WRITE.search(command):
            return "The command writes Git state in the Target Repository."
        return None
