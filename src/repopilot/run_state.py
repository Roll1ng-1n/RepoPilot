"""One internal source of mutable Run state and explicit lifecycle transitions."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from repopilot.approval import ApprovalContext, ApprovalRequest
from repopilot.budget import RunBudgetTracker
from repopilot.context import ContextManager
from repopilot.model import ToolCall
from repopilot.plan import PlanHistory
from repopilot.progress import ProgressTracker
from repopilot.recovery import RecoveryController
from repopilot.tools import ToolRegistry

TERMINAL_STATUSES = {"SUCCEEDED", "UNVERIFIED", "FAILED", "STOPPED", "BUDGET_EXCEEDED"}
RESUMABLE_STATUSES = {"STOPPED", "BUDGET_EXCEEDED", "WAITING_FOR_APPROVAL"}


@dataclass
class RunState:
    task: str
    target_repository: Path
    budget: RunBudgetTracker
    recovery: RecoveryController
    plan_history: PlanHistory
    context: ContextManager
    registry: ToolRegistry
    verifications: list[dict[str, Any]]
    approval_context: ApprovalContext
    progress: ProgressTracker
    status: str | None = None
    messages: list[dict] = field(default_factory=list)
    failures: list[dict] = field(default_factory=list)
    recoveries: list[dict] = field(default_factory=list)
    tool_results: list[dict] = field(default_factory=list)
    pending_tool_calls: list[ToolCall] = field(default_factory=list)
    approval_request: ApprovalRequest | None = None
    previous_tool_observation: str | None = None
    in_flight_tool_call: str | None = None
    approved_call_id: str | None = None
    rejected_call_id: str | None = None
    repository_baseline: dict | None = None
    completion: dict | None = None

    def transition(self, status: str, artifacts):
        if status == self.status:
            return
        allowed = (
            {"RUNNING"}
            if self.status is None or self.status in RESUMABLE_STATUSES
            else TERMINAL_STATUSES | {"WAITING_FOR_APPROVAL"}
            if self.status == "RUNNING"
            else set()
        )
        if status not in allowed:
            raise ValueError(f"Invalid Run transition: {self.status!r} -> {status!r}.")
        artifacts.append_trace("status_changed", previous_status=self.status, status=status)
        self.status = status
