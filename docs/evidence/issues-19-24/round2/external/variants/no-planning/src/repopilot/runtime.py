"""A thin native Tool Calling runtime for one Agent Run."""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jinja2 import StrictUndefined, Template

from repopilot import repository_snapshot
from repopilot.approval import ApprovalContext, ApprovalPolicy, ApprovalRequest, RiskDecision, ToolCallSnapshot
from repopilot.artifacts import RunArtifacts
from repopilot.budget import BudgetExceeded, RunBudget, RunBudgetTracker
from repopilot.checkpoint import capture_repository_state, verify_repository_state
from repopilot.context import ContextManager
from repopilot.locking import run_lock
from repopilot.model import ToolCall, ToolCallingModel
from repopilot.plan import Plan, PlanHistory, PlanStep
from repopilot.profile import repository_profile
from repopilot.recovery import (
    Failure,
    FailureCategory,
    RecoveryAction,
    RecoveryController,
    RecoveryDecision,
    classify_tool_failure,
    is_transient_model_error,
)
from repopilot.requests import RequestExecutor
from repopilot.tools import ToolRegistry

_TASK_REPORT_TEMPLATE = Template(
    """# Task report

## Root cause

{{ report.root_cause }}

## Changes

{% for change in report.changes -%}
- {{ change }}
{% endfor %}
## Rationale

{{ report.rationale }}
## Verification

{% if verifications -%}
{% for item in verifications -%}
- `{{ item.scope }}`: {{ item.reason }} ({{ "passed" if item.result.exit_code == 0 else "failed" }})
{% endfor -%}
{% else -%}
- No Task Verification was run.
{% endif %}
## Risks

{% if report.risks -%}
{% for risk in report.risks -%}
- {{ risk }}
{% endfor -%}
{% else -%}
- No risks reported.
{% endif %}
## Git commits

{% if git_commits -%}
{% for item in git_commits -%}
- `{{ item.commit_hash }}`: {{ item.reason }}
{% endfor -%}
{% else -%}
- No local Git Commits were created.
{% endif %}
""",
    undefined=StrictUndefined,
)


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
        *,
        checkpoint_model: dict[str, object] | None = None,
        checkpoint_environment: dict[str, object] | None = None,
        verifications: list[dict[str, Any]] | None = None,
        context: ContextManager | None = None,
        approval_context: ApprovalContext | None = None,
    ):
        self._model = model
        self._registry = registry
        self._registry.artifacts = artifacts
        self._artifacts = artifacts
        self._plan_history = plan_history
        self._budget = budget or RunBudget()
        self._sleeper = sleeper or time.sleep
        self._checkpoint_model = checkpoint_model or {"model_name": model.model_name}
        self._checkpoint_environment = checkpoint_environment or {}
        self._verifications = verifications if verifications is not None else []
        self._context = context or ContextManager()
        self._approval_context = approval_context or ApprovalContext(environment="unknown")
        self._approval_policy = ApprovalPolicy(self._approval_context)
        self._in_flight_tool_call: str | None = None
        self._approved_call_id: str | None = None

    def run(self, task: str, target_repository: Path, *, checkpoint=None, approval_granted=None) -> AgentRunResult:
        if self._artifacts.path.is_relative_to(target_repository.resolve()):
            raise ValueError("Agent Run artifacts must be outside the Target Repository.")
        with run_lock(self._artifacts.path):
            if checkpoint is not None:
                if checkpoint.get("schema_version", 1) not in {1, 2}:
                    raise ValueError("Unsupported Checkpoint schema version.")
                if self._artifacts.read_checkpoint() != checkpoint:
                    raise ValueError("Checkpoint changed before acquiring the run lock; reload before resuming.")
                expected = checkpoint["repository"]
                if checkpoint.get("status") == "RUNNING" and checkpoint.get("in_flight_tool_call"):
                    actual = capture_repository_state(target_repository)
                    if any(expected.get(k) != actual[k] for k in ("resolved_target_repository", "git_root")):
                        raise ValueError("Target Repository identity changed since Checkpoint.")
                else:
                    verify_repository_state(expected, target_repository)
            try:
                return self._run(task, target_repository, checkpoint=checkpoint, approval_granted=approval_granted)
            finally:
                self._registry.budget = None

    def _run(
        self,
        task: str,
        target_repository: Path,
        *,
        checkpoint: dict[str, Any] | None = None,
        approval_granted: bool | None = None,
    ) -> AgentRunResult:
        """Run a new Agent Run or continue its persisted in-progress state."""

        self._approved_call_id = checkpoint.get("approved_call_id") if checkpoint else None
        self._rejected_call_id = checkpoint.get("rejected_call_id") if checkpoint else None
        self._repository_baseline = (
            checkpoint.get("repository_baseline") if checkpoint else repository_snapshot.snapshot(target_repository)
        )
        self._target_repository = target_repository
        self._context.repository_profile = repository_profile(target_repository)
        self._registry.instruction_observer = self._context.observe_repository_instruction
        trace_status = checkpoint.get("status") if isinstance(checkpoint, dict) else None
        if not isinstance(trace_status, str):
            trace_status = None

        def record_status(status_value: str) -> None:
            nonlocal trace_status
            if status_value == trace_status:
                return
            self._artifacts.append_trace(
                "status_changed",
                previous_status=trace_status,
                status=status_value,
            )
            trace_status = status_value

        if checkpoint is None:
            budget = self._budget.start()
            recovery = RecoveryController(self._budget.max_consecutive_failures)
            failures: list[dict[str, str]] = []
            recoveries: list[dict[str, str | float]] = []
            previous_tool_observation: str | None = None
            tool_results: list[dict[str, Any]] = []
            approval_request: ApprovalRequest | None = None
            pending_tool_calls: list[ToolCall] = []
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
                "run_started",
                task=task,
                target_repository=str(target_repository.resolve()),
                model=self._model.model_name,
            )
            self._artifacts.append_trace("budget_updated", reason="run_started", budget=budget.snapshot())
            self._artifacts.append_trace("plan_created", plan=self._plan_history.current.to_dict())
        else:
            budget = RunBudgetTracker.from_snapshot(self._budget, checkpoint["budget"])
            recovery = RecoveryController(self._budget.max_consecutive_failures)
            recovery_data = checkpoint.get("recovery", {})
            if not isinstance(recovery_data, dict):
                raise ValueError("Checkpoint has invalid Recovery state.")
            recovery.restore_consecutive_failures(int(recovery_data.get("consecutive_failures", 0)))
            messages = self._checkpoint_list(checkpoint, "messages")
            failures = self._checkpoint_list(checkpoint, "failures")
            recoveries = self._checkpoint_list(checkpoint, "recoveries")
            tool_results = self._checkpoint_list(checkpoint, "tool_results")
            approval_request = self._checkpoint_approval_request(checkpoint)
            pending_tool_calls = self._checkpoint_tool_calls(checkpoint)
            previous = checkpoint.get("previous_tool_observation")
            if previous is not None and not isinstance(previous, str):
                raise ValueError("Checkpoint has an invalid Tool Call observation.")
            previous_tool_observation = previous
            context_data = checkpoint.get("context")
            if context_data is not None:
                if not isinstance(context_data, dict):
                    raise ValueError("Checkpoint has invalid Context state.")
                self._context.restore(context_data)
            if checkpoint.get("status") == "WAITING_FOR_APPROVAL" and approval_request is None:
                raise ValueError("Checkpoint is waiting for Human Approval without an Approval Request.")
            if approval_request is not None and approval_granted is None:
                raise ValueError("Human Approval is required before this Agent Run can resume.")
            self._artifacts.append_trace("run_resumed", previous_status=checkpoint.get("status"))
            self._artifacts.append_trace("budget_updated", reason="run_resumed", budget=budget.snapshot())

        if checkpoint and checkpoint.get("in_flight_tool_call"):
            uncertain_id = checkpoint["in_flight_tool_call"]
            for call in list(pending_tool_calls):
                if call.id == uncertain_id:
                    self._record_tool_result(
                        call,
                        {
                            "ok": False,
                            "error": "interrupted_result_unknown",
                            "details": "Execution may have changed repository state. Observe it before retrying; this call was not replayed.",
                        },
                        tool_results,
                        messages,
                    )
                    pending_tool_calls.remove(call)
                    self._approved_call_id = None
                    self._rejected_call_id = None
                    break
        self._in_flight_tool_call = None

        record_status("RUNNING")

        self._write_checkpoint(
            "RUNNING",
            task,
            target_repository,
            budget,
            recovery,
            messages,
            failures,
            recoveries,
            previous_tool_observation,
            tool_results,
            approval_request,
            pending_tool_calls,
        )
        if approval_request is not None:
            call = approval_request.tool_call.to_tool_call()
            self._artifacts.append_trace(
                "approval_granted" if approval_granted else "approval_rejected",
                approval_request=approval_request.to_dict(),
            )
            self._approved_call_id = call.id if approval_granted else None
            self._rejected_call_id = call.id if not approval_granted else None
            pending_tool_calls = [call, *pending_tool_calls]
            approval_request = None
        status = "FAILED"
        completion: dict[str, Any] | None = None
        self._registry.budget = budget
        self._context.output_reserve_tokens = max(
            self._context.output_reserve_tokens,
            int(self._checkpoint_model.get("model_kwargs", {}).get("max_tokens", 4096)),
        )
        executor = RequestExecutor(self._model, budget, self._artifacts)
        executor.context_window_tokens = self._context.context_window_tokens
        executor.output_reserve_tokens = self._context.output_reserve_tokens
        self._context.bind_request_executor(executor)
        try:
            while True:
                budget.remaining_seconds()
                if pending_tool_calls:
                    tool_calls = list(pending_tool_calls)
                else:
                    try:
                        budget.consume_step()
                        self._artifacts.append_trace(
                            "budget_updated", reason="agent_step_consumed", budget=budget.snapshot()
                        )
                    except BudgetExceeded as error:
                        status = self._record_budget_exhausted(error, budget)
                        break
                    try:
                        context_selection = self._context.prepare(messages, self._plan_history.current.to_dict())
                        for event in context_selection.events:
                            self._artifacts.append_trace(
                                event["type"], **{key: value for key, value in event.items() if key != "type"}
                            )
                        self._write_checkpoint(
                            "RUNNING",
                            task,
                            target_repository,
                            budget,
                            recovery,
                            messages,
                            failures,
                            recoveries,
                            previous_tool_observation,
                            tool_results,
                            approval_request,
                            pending_tool_calls,
                        )
                        turn = executor.complete(
                            self._context.bound_request(context_selection.messages, self._registry.schemas),
                            self._registry.schemas,
                        )
                        budget.remaining_seconds()
                    except BudgetExceeded:
                        raise
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
                        self._write_checkpoint(
                            "RUNNING",
                            task,
                            target_repository,
                            budget,
                            recovery,
                            messages,
                            failures,
                            recoveries,
                            previous_tool_observation,
                            tool_results,
                            approval_request,
                            pending_tool_calls,
                        )
                        continue
                    if not turn.tool_calls:
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
                        self._write_checkpoint(
                            "RUNNING",
                            task,
                            target_repository,
                            budget,
                            recovery,
                            messages,
                            failures,
                            recoveries,
                            previous_tool_observation,
                            tool_results,
                            approval_request,
                            pending_tool_calls,
                        )
                        continue
                    messages.append(self._assistant_message(turn))
                    tool_calls = turn.tool_calls
                    pending_tool_calls = list(tool_calls)
                should_finish = False
                for index, tool_call in enumerate(tool_calls):
                    budget.remaining_seconds()
                    pending_tool_calls = list(tool_calls[index:])
                    self._write_checkpoint(
                        "RUNNING",
                        task,
                        target_repository,
                        budget,
                        recovery,
                        messages,
                        failures,
                        recoveries,
                        previous_tool_observation,
                        tool_results,
                        approval_request,
                        pending_tool_calls,
                    )
                    self._artifacts.append_trace(
                        "tool_call", tool_call_id=tool_call.id, tool_name=tool_call.name, arguments=tool_call.arguments
                    )
                    if tool_call.name == "replan":
                        try:
                            budget.consume_replan()
                            self._artifacts.append_trace(
                                "budget_updated", reason="replan_consumed", budget=budget.snapshot()
                            )
                        except BudgetExceeded as error:
                            observation = {"ok": False, "error": "budget_exceeded", "limit": error.limit}
                            self._record_tool_result(tool_call, observation, tool_results, messages)
                            status = self._record_budget_exhausted(error, budget)
                            should_finish = True
                            break
                    prepared = self._registry.prepare(tool_call)
                    if tool_call.id == self._rejected_call_id:
                        observation = {
                            "ok": False,
                            "error": "approval_rejected",
                            "details": "Human Approval rejected the Tool Call.",
                        }
                    elif isinstance(prepared, dict):
                        observation = prepared
                    else:
                        assessment = self._approval_policy.assess(prepared.snapshot)
                        if assessment.decision is RiskDecision.DENY:
                            observation = {"ok": False, "error": "tool_call_denied", "details": assessment.reason}
                        elif (
                            assessment.decision is RiskDecision.REQUIRE_APPROVAL
                            and tool_call.id != self._approved_call_id
                        ):
                            approval_request = ApprovalRequest(prepared.snapshot, assessment.reason)
                            pending_tool_calls = [
                                ToolCallSnapshot.from_tool_call(remaining).to_tool_call()
                                for remaining in tool_calls[index + 1 :]
                            ]
                            self._artifacts.append_trace(
                                "approval_requested",
                                approval_request=approval_request.to_dict(),
                                pending_tool_call_ids=[call.id for call in pending_tool_calls],
                            )
                            status = "WAITING_FOR_APPROVAL"
                            should_finish = True
                            break
                        else:
                            if (
                                self._approval_context.permits_automatic_approval
                                and "Automatically approved" in assessment.reason
                            ):
                                self._artifacts.append_trace(
                                    "approval_auto_approved",
                                    tool_call=prepared.snapshot.to_dict(),
                                    reason=assessment.reason,
                                )
                            self._in_flight_tool_call = tool_call.id
                            self._write_checkpoint(
                                "RUNNING",
                                task,
                                target_repository,
                                budget,
                                recovery,
                                messages,
                                failures,
                                recoveries,
                                previous_tool_observation,
                                tool_results,
                                approval_request,
                                pending_tool_calls,
                            )
                            observation = self._registry.execute(prepared)
                    if observation.get("ok") and tool_call.name == "record_fact":
                        self._context.record_fact(observation["result"]["fact"])
                        self._artifacts.append_trace("important_fact_recorded", fact=observation["result"]["fact"])
                    self._record_tool_result(tool_call, observation, tool_results, messages)
                    self._record_git_commit(tool_call, observation)
                    self._in_flight_tool_call = None
                    if self._approved_call_id == tool_call.id:
                        self._approved_call_id = None
                    pending_tool_calls = list(tool_calls[index + 1 :])
                    self._write_checkpoint(
                        "RUNNING",
                        task,
                        target_repository,
                        budget,
                        recovery,
                        messages,
                        failures,
                        recoveries,
                        previous_tool_observation,
                        tool_results,
                        approval_request,
                        pending_tool_calls,
                    )
                    if observation.get("ok") and tool_call.name in {"update_plan", "replan"}:
                        event_type = "plan_replanned" if tool_call.name == "replan" else "plan_updated"
                        self._artifacts.append_trace(event_type, **observation["result"])
                    if (
                        tool_call.name == "finish_task"
                        and observation.get("ok")
                        and observation["result"].get("completion_allowed", True)
                    ):
                        status = observation["result"]["status"]
                        completion = observation["result"]
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
                self._write_checkpoint(
                    "RUNNING",
                    task,
                    target_repository,
                    budget,
                    recovery,
                    messages,
                    failures,
                    recoveries,
                    previous_tool_observation,
                    tool_results,
                    approval_request,
                    pending_tool_calls,
                )
        except BudgetExceeded as error:
            status = self._record_budget_exhausted(error, budget)
        except KeyboardInterrupt:
            status = "STOPPED"
            self._artifacts.append_trace("run_stopped", reason="KeyboardInterrupt")
        self._registry.budget = None
        record_status(status)
        self._artifacts.append_trace(
            "termination_audit",
            status=status,
            pending_tool_call_ids=[c.id for c in pending_tool_calls],
            uncertain_tool_call_ids=[
                item["tool_call_id"]
                for item in tool_results
                if item["observation"].get("error") == "interrupted_result_unknown"
            ],
            completion_decision=self._registry.completion_decision,
        )
        self._artifacts.append_trace(
            "budget_audit",
            complete=False,
            scope="runtime_request_and_tool_dispatch",
            budget=budget.snapshot(),
            reason="Runtime dispatch is bounded; arbitrary shell actions and provider billing are not a complete external-effects audit.",
        )
        self._artifacts.append_trace("run_finished", status=status)
        self._write_checkpoint(
            status,
            task,
            target_repository,
            budget,
            recovery,
            messages,
            failures,
            recoveries,
            previous_tool_observation,
            tool_results,
            approval_request,
            pending_tool_calls,
        )
        self._write_terminal_artifacts(status, tool_results, completion)
        self._artifacts.write_metadata(
            {
                "run_id": self._artifacts.run_id,
                "status": status,
                "task": task,
                "target_repository": str(target_repository.resolve()),
                "model": self._model.model_name,
                "plan": self._plan_history.current.to_dict(),
                "plan_history": [plan.to_dict() for plan in self._plan_history.versions],
                "context": self._context.to_checkpoint(),
                "budget": budget.snapshot(),
                "failures": failures,
                "recoveries": recoveries,
                "tool_results": tool_results,
                "verifications": self._verifications,
                "completion_decision": self._registry.completion_decision,
                "approval_context": self._approval_context.to_dict(),
                "approval_request": approval_request.to_dict() if approval_request is not None else None,
                "pending_tool_calls": [
                    ToolCallSnapshot.from_tool_call(tool_call).to_dict() for tool_call in pending_tool_calls
                ],
                "git_commits": self._git_commits(tool_results),
                "repository": capture_repository_state(target_repository),
            }
        )
        return AgentRunResult(self._artifacts.run_id, status, self._artifacts.path, self._plan_history.current)

    def resume(
        self, checkpoint: dict[str, Any], target_repository: Path, *, approval_granted: bool | None = None
    ) -> AgentRunResult:
        """Continue a stopped Agent Run from its already validated Checkpoint."""

        task = checkpoint.get("task")
        if not isinstance(task, str) or not task:
            raise ValueError("Checkpoint has no task to resume.")
        return self.run(task, target_repository, checkpoint=checkpoint, approval_granted=approval_granted)

    def _record_tool_result(
        self,
        tool_call: Any,
        observation: dict[str, Any],
        tool_results: list[dict[str, Any]],
        messages: list[dict[str, Any]],
    ) -> None:
        self._artifacts.append_trace(
            "tool_result", tool_call_id=tool_call.id, tool_name=tool_call.name, observation=observation
        )
        if tool_call.name == "verify_task" and observation.get("ok"):
            verification = observation.get("result")
            if isinstance(verification, dict):
                self._artifacts.append_trace(
                    "task_verification",
                    tool_call_id=tool_call.id,
                    command=verification.get("command"),
                    scope=verification.get("scope"),
                    reason=verification.get("reason"),
                    result=verification.get("result"),
                )
        tool_results.append(
            {
                "tool_call_id": tool_call.id,
                "tool_name": tool_call.name,
                "arguments": tool_call.arguments,
                "observation": observation,
            }
        )
        messages.append(
            {
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": json.dumps(self._registry.model_observation(observation), sort_keys=True),
            }
        )

    def _record_git_commit(self, tool_call: ToolCall, observation: dict[str, Any]) -> None:
        if tool_call.name != "git_commit" or not observation.get("ok"):
            return
        result = observation.get("result")
        if not isinstance(result, dict):
            return
        commit_hash = result.get("commit_hash")
        reason = result.get("reason")
        paths = result.get("paths")
        if not isinstance(commit_hash, str) or not isinstance(reason, str) or not isinstance(paths, list):
            return
        self._artifacts.append_trace(
            "git_commit",
            commit_hash=commit_hash,
            reason=reason,
            paths=paths,
            message=result.get("message"),
        )

    @staticmethod
    def _git_commits(tool_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        commits: list[dict[str, Any]] = []
        for item in tool_results:
            if item.get("tool_name") != "git_commit":
                continue
            observation = item.get("observation")
            if not isinstance(observation, dict) or not observation.get("ok"):
                continue
            result = observation.get("result")
            if not isinstance(result, dict):
                continue
            commit_hash = result.get("commit_hash")
            message = result.get("message")
            reason = result.get("reason")
            paths = result.get("paths")
            if (
                isinstance(commit_hash, str)
                and isinstance(message, str)
                and isinstance(reason, str)
                and isinstance(paths, list)
                and all(isinstance(path, str) for path in paths)
            ):
                commits.append({"commit_hash": commit_hash, "message": message, "reason": reason, "paths": paths})
        return commits

    def _write_checkpoint(
        self,
        status: str,
        task: str,
        target_repository: Path,
        budget: RunBudgetTracker,
        recovery: RecoveryController,
        messages: list[dict[str, Any]],
        failures: list[dict[str, str]],
        recoveries: list[dict[str, str | float]],
        previous_tool_observation: str | None,
        tool_results: list[dict[str, Any]],
        approval_request: ApprovalRequest | None = None,
        pending_tool_calls: list[ToolCall] | None = None,
    ) -> None:
        self._artifacts.write_checkpoint(
            {
                "schema_version": 2,
                "repository_baseline": self._repository_baseline,
                "approved_call_id": self._approved_call_id,
                "rejected_call_id": self._rejected_call_id,
                "in_flight_tool_call": self._in_flight_tool_call,
                "execution_log": {
                    **{
                        item["tool_call_id"]: {
                            "state": "interrupted"
                            if item["observation"].get("error") == "interrupted_result_unknown"
                            else "completed",
                            "tool_name": item["tool_name"],
                        }
                        for item in tool_results
                    },
                    **{
                        call.id: {
                            "state": "in_flight" if call.id == self._in_flight_tool_call else "pending",
                            "tool_name": call.name,
                        }
                        for call in (pending_tool_calls or [])
                    },
                },
                "run_id": self._artifacts.run_id,
                "status": status,
                "task": task,
                "model": self._checkpoint_model,
                "environment": self._checkpoint_environment,
                "plan": self._plan_history.current.to_dict(),
                "plan_history": [plan.to_dict() for plan in self._plan_history.versions],
                "context": self._context.to_checkpoint(),
                "messages": messages,
                "budget": budget.snapshot(),
                "recovery": {"consecutive_failures": recovery.consecutive_failures},
                "failures": failures,
                "recoveries": recoveries,
                "previous_tool_observation": previous_tool_observation,
                "tool_results": tool_results,
                "verifications": self._verifications,
                "completion_decision": self._registry.completion_decision,
                "approval_context": self._approval_context.to_dict(),
                "approval_request": approval_request.to_dict() if approval_request is not None else None,
                "pending_tool_calls": [
                    ToolCallSnapshot.from_tool_call(tool_call).to_dict() for tool_call in (pending_tool_calls or [])
                ],
                "repository": capture_repository_state(target_repository),
            }
        )

    @staticmethod
    def _checkpoint_list(checkpoint: dict[str, Any], key: str) -> list[Any]:
        value = checkpoint.get(key)
        if not isinstance(value, list):
            raise ValueError(f"Checkpoint has invalid {key}.")
        return value

    @staticmethod
    def _checkpoint_approval_request(checkpoint: dict[str, Any]) -> ApprovalRequest | None:
        value = checkpoint.get("approval_request")
        if value is None:
            return None
        if not isinstance(value, dict):
            raise ValueError("Checkpoint has an invalid Approval Request.")
        return ApprovalRequest.from_dict(value)

    @staticmethod
    def _checkpoint_tool_calls(checkpoint: dict[str, Any]) -> list[ToolCall]:
        value = checkpoint.get("pending_tool_calls", [])
        if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
            raise ValueError("Checkpoint has invalid pending Tool Calls.")
        return [ToolCallSnapshot.from_dict(item).to_tool_call() for item in value]

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
            self._sleeper(min(decision.retry_delay_seconds, budget.remaining_seconds()))
            budget.remaining_seconds()
        return None

    def _replan_after_failure(
        self, decision: RecoveryDecision, budget: RunBudgetTracker, messages: list[dict[str, Any]]
    ) -> str | None:
        try:
            budget.consume_replan()
            self._artifacts.append_trace("budget_updated", reason="recovery_replan_consumed", budget=budget.snapshot())
        except BudgetExceeded as error:
            return self._record_budget_exhausted(error, budget)
        messages.append({"role": "user", "content": f"Recovery Observation: {decision.reason}"})
        return None
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

    def _write_terminal_artifacts(
        self,
        status: str,
        tool_results: list[dict[str, Any]],
        completion: dict[str, Any] | None,
    ) -> None:
        """Write the complete machine- and human-readable terminal deliverables."""

        verifications = self._verifications
        report: dict[str, Any]
        final_patch = ""
        if completion is not None:
            candidate_verifications = completion.get("verifications")
            if isinstance(candidate_verifications, list):
                verifications = candidate_verifications
            candidate_report = completion.get("report")
            if isinstance(candidate_report, dict):
                report = candidate_report
            else:
                report = self._status_report(status)
            candidate_patch = completion.get("final_patch")
            if isinstance(candidate_patch, str):
                final_patch = candidate_patch
        else:
            report = self._status_report(status)

        if not final_patch:
            final_patch = self._capture_patch(tool_results)
        self._artifacts.write_json(
            "plan.json",
            {
                "current": self._plan_history.current.to_dict(),
                "history": [plan.to_dict() for plan in self._plan_history.versions],
            },
        )
        final_snapshot = repository_snapshot.snapshot(self._target_repository)
        baseline = self._repository_baseline
        patch_scope = "unsupported_legacy_or_non_git"
        if baseline and baseline.get("tree") and final_snapshot.get("tree"):
            self._artifacts.write_text("worktree.diff", final_patch)
            initial_state = baseline["state"]
            self._artifacts.write_text(
                "initial-worktree.diff",
                repository_snapshot.diff(self._target_repository, initial_state["head"], baseline["tree"]),
            )
            final_patch = repository_snapshot.diff(self._target_repository, baseline["tree"], final_snapshot["tree"])
            patch_scope = "agent_run_content_delta"
        self._artifacts.write_text("patch.diff", final_patch)
        persisted = (self._artifacts.path / "patch.diff").read_bytes()
        self._artifacts.write_json(
            "patch-manifest.json",
            {
                "scope": patch_scope,
                "baseline": baseline,
                "final": final_snapshot,
                "bytes": len(persisted),
                "sha256": hashlib.sha256(persisted).hexdigest(),
                "replay": "Apply initial-worktree.diff to baseline HEAD, then patch.diff.",
            },
        )
        self._artifacts.write_json("verification.json", {"verifications": verifications})
        self._artifacts.write_text(
            "task_report.md",
            self._format_task_report(report, verifications, self._git_commits(tool_results))
            + "\n## Completion decision\n\n```json\n"
            + json.dumps(self._registry.completion_decision, indent=2)
            + "\n```\n",
        )

    def _capture_patch(self, tool_results: list[dict[str, Any]]) -> str:
        """Capture the final diff, retaining pre-commit patches as a fallback."""

        diff_observation = self._registry.capture_diff()
        if diff_observation.get("ok"):
            result = diff_observation.get("result")
            if isinstance(result, dict) and isinstance(result.get("patch"), str) and result["patch"]:
                return result["patch"]

        patches: list[str] = []
        for item in tool_results:
            if item.get("tool_name") != "git_commit":
                continue
            commit_observation = item.get("observation")
            if not isinstance(commit_observation, dict) or not commit_observation.get("ok"):
                continue
            commit_result = commit_observation.get("result")
            if (
                isinstance(commit_result, dict)
                and isinstance(commit_result.get("patch"), str)
                and commit_result["patch"]
            ):
                patches.append(commit_result["patch"])
        return "\n".join(patches)

    @staticmethod
    def _status_report(status: str) -> dict[str, Any]:
        return {
            "root_cause": f"The Agent Run paused or ended with status {status} before a completion report was provided.",
            "changes": ["No completion report was provided by the model."],
            "rationale": f"The terminal status was {status}.",
            "risks": ["The requested work may be incomplete or lack sufficient Task Verification evidence."],
        }

    @staticmethod
    def _format_task_report(
        report: dict[str, Any], verifications: list[dict[str, Any]], git_commits: list[dict[str, Any]]
    ) -> str:
        normalized_report = {
            "root_cause": report.get("root_cause") or "No root cause was provided.",
            "changes": report.get("changes") or ["No changes were reported."],
            "rationale": report.get("rationale") or "No overall modification rationale was provided.",
            "risks": report.get("risks") or [],
        }
        return (
            _TASK_REPORT_TEMPLATE.render(
                report=normalized_report,
                verifications=verifications,
                git_commits=git_commits,
            ).strip()
            + "\n"
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
