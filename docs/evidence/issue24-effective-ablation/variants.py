"""Isolated experimental switches; production defaults are the full control."""

from __future__ import annotations

import json
from contextlib import ExitStack, contextmanager
from unittest.mock import patch

VARIANTS = ("full", "no-profile", "no-context-selection", "no-planning", "no-recovery")


@contextmanager
def variant_context(variant, telemetry):
    import repopilot.benchmark as benchmark
    import repopilot.runtime as runtime
    from repopilot.budget import BudgetExceeded
    from repopilot.context import ContextManager
    from repopilot.recovery import FailureCategory, RecoveryAction, RecoveryController, RecoveryDecision

    registry_factory = benchmark.create_tool_registry
    profile_factory = runtime.repository_profile
    recover = RecoveryController.recover

    class ObservedContext(ContextManager):
        def bound_request(self, messages, schemas):
            before = len(json.dumps({"messages": messages, "tools": schemas}, ensure_ascii=False).encode())
            event = {
                "variant": variant,
                "messages_before": len(messages),
                "input_bytes_before": before,
                "profile_fact_count": len((self.repository_profile or {}).get("facts", [])),
                "instruction_sources": [i["source"] for i in (self.repository_profile or {}).get("instructions", [])],
                "planning_enabled": self.include_plan,
            }
            try:
                if variant == "no-context-selection":
                    # Disable both selection and generic trimming, but never send an oversized request.
                    if before + self.output_reserve_tokens + 1024 > self.context_window_tokens:
                        event["context_limit_reached"] = True
                        raise BudgetExceeded("context_window")
                    selected = messages
                else:
                    selected = super().bound_request(messages, schemas)
                event["messages_after"] = len(selected)
                event["input_bytes_after"] = len(
                    json.dumps({"messages": selected, "tools": schemas}, ensure_ascii=False).encode()
                )
                event["context_changed"] = selected != messages
                return selected
            finally:
                if telemetry is not None:
                    with telemetry.open("a") as stream:
                        stream.write(json.dumps(event) + "\n")

    def profile(root):
        result = profile_factory(root)
        if variant == "no-profile":
            result["facts"] = []
        return result

    def registry(*args, **kwargs):
        return registry_factory(*args, **kwargs, planning_enabled=variant != "no-planning")

    def recovery(self, failure, *, transient_model_error=False):
        # Transport retries are preserved in every arm, per the user's latency policy.
        if variant == "no-recovery" and failure.category is not FailureCategory.MODEL_ERROR:
            self.consecutive_failures += 1
            return RecoveryDecision(RecoveryAction.STOP, "Task/protocol recovery disabled for this experiment.")
        return recover(self, failure, transient_model_error=transient_model_error)

    with ExitStack() as stack:
        stack.enter_context(patch.object(benchmark, "ContextManager", ObservedContext))
        stack.enter_context(patch.object(benchmark, "create_tool_registry", registry))
        stack.enter_context(patch.object(runtime, "repository_profile", profile))
        stack.enter_context(patch.object(RecoveryController, "recover", recovery))
        yield
