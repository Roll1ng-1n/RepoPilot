"""A thin native Tool Calling runtime for one Agent Run."""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from repopilot.artifacts import RunArtifacts
from repopilot.budget import BudgetExceeded, RunBudget, RunBudgetTracker
from repopilot.model import ToolCallingModel
from repopilot.plan import Plan, PlanHistory, PlanStep
from repopilot.recovery import (
    Failure,
    FailureCategory,
    RecoveryAction,
    RecoveryController,
    RecoveryDecision,
    classify_tool_failure,
    is_transient_model_error,
)
from repopilot.tools import ToolRegistry


@dataclass(frozen=True)
class AgentRunResult:
    run_id: str
    status: str
    artifact_directory: Path
    plan: Plan


class AgentRuntime:
    """Drives a model and Tool Registry without knowing an Environment implementation."""

    def __init__(
        self,
        model: ToolCallingModel,
        registry: ToolRegistry,
        artifacts: RunArtifacts,
        plan_history: PlanHistory,
        budget: RunBudget | None = None,
        sleeper: Callable[[float], None] | None = None,
    ):
        self._model = model
        self._registry = registry
        self._artifacts = artifacts
        self._plan_history = plan_history
        self._budget = budget or RunBudget()
        self._sleeper = sleeper or time.sleep

    def run(self, task: str, target_repository: Path) -> AgentRunResult:
        budget = self._budget.start()
        recovery = RecoveryController(self._budget.max_consecutive_failures)
        failures: list[dict[str, str]] = []
        recoveries: list[dict[str, str | float]] = []
        previous_tool_observation: str | None = None
        messages: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": (
                    "Use the provided native tools to inspect the Target Repository. Do not emit text actions. "
                    "Use the Agent Control Tools to update the explicit Plan, Replan when new facts change the "
                    "unfinished work, and request task completion with finish_task. Current Plan: "
                    f"{json.dumps(self._plan_history.current.to_dict(), sort_keys=True)}"
                ),
            },
            {"role": "user", "content": task},
        ]
        self._artifacts.append_trace(
            "run_started", task=task, target_repository=str(target_repository.resolve()), model=self._model.model_name
        )
        self._artifacts.append_trace("plan_created", plan=self._plan_history.current.to_dict())
        status = "FAILED"
        while True:
            try:
                budget.consume_step()
            except BudgetExceeded as error:
                status = self._record_budget_exhausted(error, budget)
                break
            try:
                turn = self._model.complete(messages, self._registry.schemas)
            except Exception as error:
                terminal_status = self._handle_failure(
                    Failure(FailureCategory.MODEL_ERROR, str(error) or type(error).__name__),
                    recovery,
                    budget,
                    messages,
                    failures,
                    recoveries,
                    transient_model_error=is_transient_model_error(error),
                )
                if terminal_status is not None:
                    status = terminal_status
                    break
                continue
            if not turn.tool_calls:
                self._artifacts.append_trace("model_response", content=turn.content or "")
                messages.append(self._assistant_message(turn))
                terminal_status = self._handle_failure(
                    Failure(FailureCategory.NO_PROGRESS, "The model response contained no Tool Call."),
                    recovery,
                    budget,
                    messages,
                    failures,
                    recoveries,
                )
                if terminal_status is not None:
                    status = terminal_status
                    break
                continue
            messages.append(self._assistant_message(turn))
            should_finish = False
            for tool_call in turn.tool_calls:
                self._artifacts.append_trace(
                    "tool_call", tool_call_id=tool_call.id, tool_name=tool_call.name, arguments=tool_call.arguments
                )
                observation: dict[str, Any]
                if tool_call.name == "replan":
                    try:
                        budget.consume_replan()
                    except BudgetExceeded as error:
                        observation = {"ok": False, "error": "budget_exceeded", "limit": error.limit}
                        self._artifacts.append_trace(
                            "tool_result", tool_call_id=tool_call.id, tool_name=tool_call.name, observation=observation
                        )
                        status = self._record_budget_exhausted(error, budget)
                        should_finish = True
                        break
                observation = self._registry.dispatch(tool_call)
                self._artifacts.append_trace(
                    "tool_result", tool_call_id=tool_call.id, tool_name=tool_call.name, observation=observation
                )
                if observation.get("ok") and tool_call.name in {"update_plan", "replan"}:
                    event_type = "plan_replanned" if tool_call.name == "replan" else "plan_updated"
                    self._artifacts.append_trace(event_type, **observation["result"])
                messages.append(
                    {"role": "tool", "tool_call_id": tool_call.id, "content": json.dumps(observation, sort_keys=True)}
                )
                if tool_call.name == "finish_task" and observation.get("ok"):
                    status = observation["result"]["status"]
                    self._write_terminal_artifacts(observation["result"])
                    should_finish = True
                    break
                failure = classify_tool_failure(tool_call.name, observation)
                observation_signature = self._tool_observation_signature(
                    tool_call.name, tool_call.arguments, observation
                )
                if failure is None and observation_signature == previous_tool_observation:
                    failure = Failure(
                        FailureCategory.NO_PROGRESS,
                        "The Tool Call and its Observation repeated without new progress.",
                        tool_call.name,
                    )
                previous_tool_observation = observation_signature
                if failure is None:
                    recovery.record_success()
                    continue
                terminal_status = self._handle_failure(
                    failure,
                    recovery,
                    budget,
                    messages,
                    failures,
                    recoveries,
                )
                if terminal_status is not None:
                    status = terminal_status
                    should_finish = True
                    break
            if should_finish:
                break
        self._artifacts.append_trace("run_finished", status=status)
        self._artifacts.write_metadata(
            {
                "run_id": self._artifacts.run_id,
                "status": status,
                "target_repository": str(target_repository.resolve()),
                "model": self._model.model_name,
                "plan": self._plan_history.current.to_dict(),
                "plan_history": [plan.to_dict() for plan in self._plan_history.versions],
                "budget": budget.snapshot(),
                "failures": failures,
                "recoveries": recoveries,
            }
        )
        return AgentRunResult(self._artifacts.run_id, status, self._artifacts.path, self._plan_history.current)

    def _handle_failure(
        self,
        failure: Failure,
        recovery: RecoveryController,
        budget: RunBudgetTracker,
        messages: list[dict[str, Any]],
        failures: list[dict[str, str]],
        recoveries: list[dict[str, str | float]],
        *,
        transient_model_error: bool = False,
    ) -> str | None:
        failure_data = failure.to_dict()
        failures.append(failure_data)
        self._artifacts.append_trace("failure", **failure_data)
        decision = recovery.recover(failure, transient_model_error=transient_model_error)
        recovery_data = {**decision.to_dict(), "category": failure.category.value}
        recoveries.append(recovery_data)
        self._artifacts.append_trace("recovery", **recovery_data)
        if decision.action is RecoveryAction.STOP:
            return "FAILED"
        if decision.action is RecoveryAction.REPLAN:
            terminal_status = self._replan_after_failure(decision, budget, messages)
            if terminal_status is None:
                recovery.record_success()
            return terminal_status
        messages.append(
            {
                "role": "user",
                "content": f"Recovery Observation ({failure.category.value}): {decision.reason}",
            }
        )
        if decision.action is RecoveryAction.RETRY_MODEL:
            self._sleeper(decision.retry_delay_seconds)
        return None

    def _replan_after_failure(
        self, decision: RecoveryDecision, budget: RunBudgetTracker, messages: list[dict[str, Any]]
    ) -> str | None:
        try:
            budget.consume_replan()
        except BudgetExceeded as error:
            return self._record_budget_exhausted(error, budget)
        step_id = self._next_recovery_step_id(budget)
        replanned = self._plan_history.replan(
            [
                PlanStep(
                    step_id,
                    "Recover using a revised approach.",
                    "A corrected approach has produced new Task Verification evidence.",
                )
            ],
            decision.reason,
        )
        self._artifacts.append_trace("plan_replanned", plan=replanned.to_dict(), reason=decision.reason)
        messages.append(
            {
                "role": "user",
                "content": f"Recovery Observation: Plan v{replanned.version} was created because {decision.reason}",
            }
        )
        return None

    def _record_budget_exhausted(self, error: BudgetExceeded, budget: RunBudgetTracker) -> str:
        self._artifacts.append_trace("budget_exhausted", limit=error.limit, budget=budget.snapshot())
        return "BUDGET_EXCEEDED"

    def _next_recovery_step_id(self, budget: RunBudgetTracker) -> str:
        existing_ids = {step.id for step in self._plan_history.current.steps}
        base_id = f"recovery-{budget.replans_used}"
        step_id = base_id
        suffix = 2
        while step_id in existing_ids:
            step_id = f"{base_id}-{suffix}"
            suffix += 1
        return step_id

    @staticmethod
    def _tool_observation_signature(tool_name: str, arguments: dict[str, Any], observation: dict[str, Any]) -> str:
        return json.dumps(
            {
                "tool_name": tool_name,
                "arguments": arguments,
                "observation": AgentRuntime._without_volatile_timing(observation),
            },
            sort_keys=True,
            default=str,
        )

    @staticmethod
    def _without_volatile_timing(value: Any) -> Any:
        if isinstance(value, dict):
            return {
                key: AgentRuntime._without_volatile_timing(item)
                for key, item in value.items()
                if key != "duration_seconds"
            }
        if isinstance(value, list):
            return [AgentRuntime._without_volatile_timing(item) for item in value]
        return value

    def _write_terminal_artifacts(self, completion: dict[str, Any]) -> None:
        self._artifacts.write_text("patch.diff", completion["final_patch"])
        self._artifacts.write_json("verification.json", {"verifications": completion["verifications"]})
        report = completion["report"]
        self._artifacts.write_text(
            "task_report.md",
            self._format_task_report(report, completion["verifications"]),
        )

    @staticmethod
    def _format_task_report(report: dict[str, Any], verifications: list[dict[str, Any]]) -> str:
        verification_lines = [
            f"- `{item['scope']}`: {item['reason']} ({'passed' if item['result']['exit_code'] == 0 else 'failed'})"
            for item in verifications
        ] or ["- No Task Verification was run."]
        risk_lines = [f"- {risk}" for risk in report["risks"]] or ["- No risks reported."]
        return "\n".join(
            [
                "# Task report",
                "",
                "## Root cause",
                "",
                report["root_cause"],
                "",
                "## Changes",
                "",
                *(f"- {change}" for change in report["changes"]),
                "",
                "## Verification",
                "",
                *verification_lines,
                "",
                "## Risks",
                "",
                *risk_lines,
                "",
            ]
        )

    @staticmethod
    def _assistant_message(turn: Any) -> dict[str, Any]:
        return {
            "role": "assistant",
            "content": turn.content,
            "tool_calls": [
                {
                    "id": tool_call.id,
                    "type": "function",
                    "function": {"name": tool_call.name, "arguments": json.dumps(tool_call.arguments, sort_keys=True)},
                }
                for tool_call in turn.tool_calls
            ],
        }
