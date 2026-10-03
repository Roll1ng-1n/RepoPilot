"""Verification evidence selection and final-source completion decisions."""

from __future__ import annotations

from repopilot.plan import PlanInvariantError, PlanStepStatus


class VerificationGate:
    def __init__(self, verifications, plan_history, required_verifications=()):
        self.verifications = verifications
        self.plan_history = plan_history
        self.required_verifications = required_verifications

    def prepare(self, arguments):
        plan_ids = {step.id for step in self.plan_history.current.steps}
        step_ids = getattr(arguments, "step_ids", []) or sorted(plan_ids)
        if not set(step_ids) <= plan_ids:
            raise PlanInvariantError(
                f"Verification references an unknown Plan Step. Omit step_ids for task-level verification, or use {sorted(plan_ids)}."
            )
        if not set(arguments.supersedes) <= {v["sequence"] for v in self.verifications}:
            raise ValueError("supersedes references an unknown verification sequence.")
        check_id = arguments.check_id
        previous = None
        if check_id is None:
            previous = next((v for v in reversed(self.verifications) if v["command"] == arguments.command), None)
            if previous is None:
                previous = next(
                    (
                        v
                        for v in reversed(self.verifications)
                        if v["scope"] == arguments.scope and not v.get("explicit_check_id")
                    ),
                    None,
                )
            check_id = (
                previous.get("check_id", previous["scope"])
                if previous
                else f"verification-{len(self.verifications) + 1}"
            )
        return check_id, previous, step_ids

    def evaluate(self, fingerprint):
        replaced = {sequence for item in self.verifications for sequence in item.get("supersedes", [])}
        latest = {
            item.get("check_id", item["scope"]): item
            for item in self.verifications
            if item.get("sequence") not in replaced
        }
        problems = []
        for check_id, item in latest.items():
            identity = {"scope": item["scope"], "check_id": check_id, "sequence": item.get("sequence")}
            if item["result"]["exit_code"] != 0:
                problems.append({**identity, "reason": "failed"})
            elif item.get("before_fingerprint") != fingerprint or item.get("after_fingerprint") != fingerprint:
                problems.append({**identity, "reason": "stale_or_mutating_verification"})
        by_command = {item["command"]: item for item in self.verifications}
        for command in self.required_verifications:
            item = by_command.get(command)
            if (
                item is None
                or item["result"]["exit_code"] != 0
                or any(item.get(key) != fingerprint for key in ("before_fingerprint", "after_fingerprint"))
            ):
                problems.append({"command": command, "reason": "required_check_not_satisfied"})
        covered = {
            step_id
            for item in latest.values()
            if item["result"]["exit_code"] == 0
            and item.get("before_fingerprint") == fingerprint
            and item.get("after_fingerprint") == fingerprint
            for step_id in item.get("plan_step_ids", [])
        }
        if self.verifications:
            for step in self.plan_history.current.steps:
                if step.status is not PlanStepStatus.SKIPPED and step.id not in covered:
                    problems.append({"step_id": step.id, "reason": "plan_step_has_no_current_verification"})
        return {
            "fingerprint": fingerprint,
            "required_verifications": list(self.required_verifications),
            "evidence_scope": "required_commands" if self.required_verifications else "model_selected_checks",
            "covered_plan_steps": sorted(covered),
            "problems": problems,
            "completion_allowed": not problems,
            "verification_sequences": [v.get("sequence") for v in latest.values()],
        }
