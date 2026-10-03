"""Map composed RunState to schema 2 without changing the persistence format."""

from __future__ import annotations

from repopilot.approval import ApprovalRequest, ToolCallSnapshot
from repopilot.budget import RunBudgetTracker
from repopilot.progress import ProgressTracker
from repopilot.run_state import RESUMABLE_STATUSES, TERMINAL_STATUSES


class CheckpointCodec:
    @staticmethod
    def encode(state, *, run_id, model, environment, repository):
        return {
            "schema_version": 2,
            "run_id": run_id,
            "status": state.status,
            "task": state.task,
            "model": model,
            "environment": environment,
            "repository": repository,
            "repository_baseline": state.repository_baseline,
            "progress_tracker": state.progress.to_checkpoint(),
            "approved_call_id": state.approved_call_id,
            "rejected_call_id": state.rejected_call_id,
            "in_flight_tool_call": state.in_flight_tool_call,
            "execution_log": {
                **{
                    item["tool_call_id"]: {
                        "state": "interrupted"
                        if item["observation"].get("error") == "interrupted_result_unknown"
                        else "completed",
                        "tool_name": item["tool_name"],
                    }
                    for item in state.tool_results
                },
                **{
                    call.id: {
                        "state": "in_flight" if call.id == state.in_flight_tool_call else "pending",
                        "tool_name": call.name,
                    }
                    for call in state.pending_tool_calls
                },
            },
            "plan": state.plan_history.current.to_dict(),
            "plan_history": [plan.to_dict() for plan in state.plan_history.versions],
            "context": state.context.to_checkpoint(),
            "messages": state.messages,
            "budget": state.budget.snapshot(),
            "recovery": state.recovery.to_checkpoint(),
            "failures": state.failures,
            "recoveries": state.recoveries,
            "previous_tool_observation": state.previous_tool_observation,
            "tool_results": state.tool_results,
            "verifications": state.verifications,
            "completion_decision": state.registry.completion_decision,
            "approval_context": state.approval_context.to_dict(),
            "approval_request": state.approval_request.to_dict() if state.approval_request else None,
            "pending_tool_calls": [
                ToolCallSnapshot.from_tool_call(call).to_dict() for call in state.pending_tool_calls
            ],
        }

    @staticmethod
    def restore(state, checkpoint, budget_options):
        if checkpoint.get("schema_version", 1) not in {1, 2}:
            raise ValueError("Unsupported Checkpoint schema version.")
        status = checkpoint.get("status")
        if status not in {"RUNNING"} | TERMINAL_STATUSES | RESUMABLE_STATUSES:
            raise ValueError("Checkpoint has an invalid Run status.")
        state.status = status
        if not isinstance(checkpoint.get("budget"), dict):
            raise ValueError("Checkpoint has invalid budget.")
        state.budget = RunBudgetTracker.from_snapshot(budget_options, checkpoint["budget"])
        for key in ("messages", "failures", "recoveries", "tool_results"):
            value = checkpoint.get(key)
            if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
                raise ValueError(f"Checkpoint has invalid {key}.")
            setattr(state, key, value)
        recovery = checkpoint.get("recovery", {})
        if not isinstance(recovery, dict):
            raise ValueError("Checkpoint has invalid Recovery state.")
        state.recovery.restore(recovery, state.failures)
        previous = checkpoint.get("previous_tool_observation")
        if previous is not None and not isinstance(previous, str):
            raise ValueError("Checkpoint has an invalid Tool Call observation.")
        state.previous_tool_observation = previous
        context = checkpoint.get("context")
        if context is not None:
            if not isinstance(context, dict):
                raise ValueError("Checkpoint has invalid Context state.")
            state.context.restore(context)
        approval = checkpoint.get("approval_request")
        if approval is not None and not isinstance(approval, dict):
            raise ValueError("Checkpoint has an invalid Approval Request.")
        state.approval_request = ApprovalRequest.from_dict(approval) if approval else None
        pending = checkpoint.get("pending_tool_calls", [])
        if not isinstance(pending, list) or not all(isinstance(item, dict) for item in pending):
            raise ValueError("Checkpoint has invalid pending Tool Calls.")
        state.pending_tool_calls = [ToolCallSnapshot.from_dict(item).to_tool_call() for item in pending]
        for key in ("approved_call_id", "rejected_call_id", "in_flight_tool_call"):
            value = checkpoint.get(key)
            if value is not None and not isinstance(value, str):
                raise ValueError(f"Checkpoint has invalid {key}.")
            setattr(state, key, value)
        state.repository_baseline = checkpoint.get("repository_baseline")
        verifications = checkpoint.get("verifications", [])
        if not isinstance(verifications, list) or not all(isinstance(item, dict) for item in verifications):
            raise ValueError("Checkpoint has invalid Task Verifications.")
        # Keep the same list captured by the Tool Registry and VerificationGate.
        state.verifications[:] = verifications
        if "progress_tracker" in checkpoint:
            state.progress = ProgressTracker.from_checkpoint(checkpoint["progress_tracker"])
        state.registry.completion_decision = checkpoint.get("completion_decision") or {}
