"""Versioned Plans and Replans for a bounded Agent Run."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from enum import Enum


class PlanInvariantError(ValueError):
    """Raised when a Plan would violate its state constraints."""


class PlanStepStatus(str, Enum):
    """A Plan Step's supported lifecycle states."""

    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


@dataclass(frozen=True)
class PlanStep:
    """One ordered, verifiable unit of an Agent Run's Plan."""

    id: str
    description: str
    completion_condition: str
    status: PlanStepStatus = PlanStepStatus.PENDING

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise PlanInvariantError("A Plan Step id must not be empty.")
        if not self.description.strip():
            raise PlanInvariantError("A Plan Step description must not be empty.")
        if not self.completion_condition.strip():
            raise PlanInvariantError("A Plan Step completion condition must not be empty.")

    def to_dict(self) -> dict[str, str]:
        return {
            "id": self.id,
            "description": self.description,
            "completion_condition": self.completion_condition,
            "status": self.status.value,
        }

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> PlanStep:
        """Recreate a persisted Plan Step while retaining its lifecycle state."""

        try:
            return cls(
                id=str(value["id"]),
                description=str(value["description"]),
                completion_condition=str(value["completion_condition"]),
                status=PlanStepStatus(str(value["status"])),
            )
        except (KeyError, ValueError) as error:
            raise PlanInvariantError("Invalid persisted Plan Step.") from error


@dataclass(frozen=True)
class Plan:
    """One numbered snapshot of the ordered work for an Agent Run."""

    version: int
    steps: tuple[PlanStep, ...]
    reason: str

    def __post_init__(self) -> None:
        if self.version < 1:
            raise PlanInvariantError("A Plan version must be positive.")
        if not self.steps:
            raise PlanInvariantError("A Plan must contain at least one Plan Step.")
        if not self.reason.strip():
            raise PlanInvariantError("A Plan reason must not be empty.")
        step_ids = [step.id for step in self.steps]
        if len(step_ids) != len(set(step_ids)):
            raise PlanInvariantError("A Plan must not contain duplicate Plan Step ids.")
        if sum(step.status is PlanStepStatus.IN_PROGRESS for step in self.steps) > 1:
            raise PlanInvariantError("A Plan may have at most one IN_PROGRESS Plan Step.")

    def update_step(self, step_id: str, status: PlanStepStatus) -> Plan:
        """Return this version with one Plan Step's status changed."""

        if not any(step.id == step_id for step in self.steps):
            raise PlanInvariantError(f"Unknown Plan Step id: {step_id}")
        return replace(
            self,
            steps=tuple(replace(step, status=status) if step.id == step_id else step for step in self.steps),
        )

    def replan(self, replacement_steps: Sequence[PlanStep], reason: str) -> Plan:
        """Create the next version, retaining only completed work from this one."""

        if any(step.status is not PlanStepStatus.PENDING for step in replacement_steps):
            raise PlanInvariantError("Replacement Plan Steps must start PENDING.")
        completed_steps = tuple(step for step in self.steps if step.status is PlanStepStatus.COMPLETED)
        return Plan(self.version + 1, completed_steps + tuple(replacement_steps), reason)

    def to_dict(self) -> dict[str, object]:
        return {
            "version": self.version,
            "reason": self.reason,
            "steps": [step.to_dict() for step in self.steps],
        }

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> Plan:
        """Recreate one persisted Plan version."""

        try:
            steps = value["steps"]
            if not isinstance(steps, list):
                raise PlanInvariantError("Persisted Plan Steps must be a list.")
            version = value["version"]
            reason = value["reason"]
            if not isinstance(version, int) or isinstance(version, bool) or not isinstance(reason, str):
                raise PlanInvariantError("Persisted Plan has invalid fields.")
            return cls(
                version=version,
                steps=tuple(PlanStep.from_dict(step) for step in steps if isinstance(step, dict)),
                reason=reason,
            )
        except (KeyError, TypeError, ValueError) as error:
            raise PlanInvariantError("Invalid persisted Plan.") from error


class PlanHistory:
    """The mutable version history owned by one Agent Run."""

    def __init__(self, initial_plan: Plan):
        self._versions = [initial_plan]

    @classmethod
    def for_task(cls, task: str) -> PlanHistory:
        """Start every Agent Run with one bounded, explicit Plan Step."""

        return cls(
            Plan(
                version=1,
                steps=(
                    PlanStep(
                        id="complete-task",
                        description=task,
                        completion_condition="The requested task is completed and Task Verification has run.",
                    ),
                ),
                reason="Initial Plan for this Agent Run.",
            )
        )

    @property
    def current(self) -> Plan:
        return self._versions[-1]

    @property
    def versions(self) -> tuple[Plan, ...]:
        return tuple(self._versions)

    def update_step(self, step_id: str, status: PlanStepStatus) -> Plan:
        """Persist a state change in the current Plan version."""

        updated = self.current.update_step(step_id, status)
        self._versions[-1] = updated
        return updated

    def replan(self, replacement_steps: Sequence[PlanStep], reason: str) -> Plan:
        """Persist the next Plan version with completed work retained."""

        replanned = self.current.replan(replacement_steps, reason)
        self._versions.append(replanned)
        return replanned

    @classmethod
    def from_dict(cls, versions: list[dict[str, object]]) -> PlanHistory:
        """Restore the complete version history of a persisted Plan."""

        if not versions:
            raise PlanInvariantError("A persisted Plan History must contain a Plan.")
        restored_versions = [Plan.from_dict(value) for value in versions]
        history = cls(restored_versions[0])
        history._versions = restored_versions
        return history
