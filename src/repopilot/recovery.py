"""Failure classification and bounded Recovery decisions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class FailureCategory(str, Enum):
    """The externally visible reasons an Agent Run could not advance."""

    MODEL_ERROR = "MODEL_ERROR"
    TOOL_ERROR = "TOOL_ERROR"
    ENVIRONMENT_ERROR = "ENVIRONMENT_ERROR"
    VERIFICATION_FAILURE = "VERIFICATION_FAILURE"
    NO_PROGRESS = "NO_PROGRESS"


class RecoveryAction(str, Enum):
    """The bounded action selected after one failed attempt."""

    RETRY_MODEL = "RETRY_MODEL"
    RETURN_OBSERVATION = "RETURN_OBSERVATION"
    DEBUG_OBSERVATION = "DEBUG_OBSERVATION"
    REPLAN = "REPLAN"
    STOP = "STOP"


@dataclass(frozen=True)
class Failure:
    category: FailureCategory
    reason: str
    tool_name: str | None = None

    def to_dict(self) -> dict[str, str]:
        result = {"category": self.category.value, "reason": self.reason}
        if self.tool_name is not None:
            result["tool_name"] = self.tool_name
        return result


@dataclass(frozen=True)
class RecoveryDecision:
    action: RecoveryAction
    reason: str
    retry_delay_seconds: float = 0.0

    def to_dict(self) -> dict[str, str | float]:
        return {
            "action": self.action.value,
            "reason": self.reason,
            "retry_delay_seconds": self.retry_delay_seconds,
        }


class RecoveryController:
    """Turns failures into bounded Recovery actions."""

    def __init__(self, max_consecutive_failures: int, *, initial_retry_delay_seconds: float = 0.25):
        self._max_consecutive_failures = max_consecutive_failures
        self._initial_retry_delay_seconds = initial_retry_delay_seconds
        self.consecutive_failures = 0

    def record_success(self) -> None:
        self.consecutive_failures = 0

    def restore_consecutive_failures(self, value: int) -> None:
        """Restore the bounded recovery counter from a Checkpoint."""

        if value < 0:
            raise ValueError("Checkpoint has an invalid consecutive failure counter.")
        self.consecutive_failures = value

    def recover(self, failure: Failure, *, transient_model_error: bool = False) -> RecoveryDecision:
        self.consecutive_failures += 1
        if self.consecutive_failures >= self._max_consecutive_failures:
            return RecoveryDecision(
                RecoveryAction.REPLAN,
                f"{self.consecutive_failures} consecutive failures require a Replan: {failure.reason}",
            )
        if failure.category is FailureCategory.MODEL_ERROR and transient_model_error:
            delay = self._initial_retry_delay_seconds * (2 ** (self.consecutive_failures - 1))
            return RecoveryDecision(
                RecoveryAction.RETRY_MODEL,
                f"Retrying a transient model error after {delay:g} seconds: {failure.reason}",
                delay,
            )
        if failure.category is FailureCategory.VERIFICATION_FAILURE:
            return RecoveryDecision(
                RecoveryAction.DEBUG_OBSERVATION,
                f"Use the failed Task Verification as a debugging Observation: {failure.reason}",
            )
        if failure.category is FailureCategory.MODEL_ERROR:
            return RecoveryDecision(RecoveryAction.STOP, f"The model error is not transient: {failure.reason}")
        return RecoveryDecision(
            RecoveryAction.RETURN_OBSERVATION, f"Return an Observation for correction: {failure.reason}"
        )


def classify_tool_failure(tool_name: str, observation: dict[str, Any]) -> Failure | None:
    """Classify structured Tool observations without depending on an Environment type."""
    if not observation.get("ok"):
        category = (
            FailureCategory.ENVIRONMENT_ERROR
            if observation.get("error") == "environment_error"
            else FailureCategory.TOOL_ERROR
        )
        return Failure(category, str(observation.get("details") or observation.get("error")), tool_name)

    command_result = _command_result(observation)
    if tool_name == "verify_task" and command_result and command_result.get("exit_code") != 0:
        return Failure(
            FailureCategory.VERIFICATION_FAILURE,
            f"Task Verification exited with {command_result['exit_code']}.",
            tool_name,
        )
    if command_result and command_result.get("exit_code") == -1:
        return Failure(
            FailureCategory.ENVIRONMENT_ERROR, "The Execution Environment could not run a command.", tool_name
        )
    return None


def is_transient_model_error(error: Exception) -> bool:
    """Recognize provider failures for which a bounded backoff is useful."""
    if isinstance(error, (TimeoutError, ConnectionError)):
        return True
    status_code = getattr(error, "status_code", None)
    if isinstance(status_code, int) and (status_code in {408, 409, 425, 429} or status_code >= 500):
        return True
    error_name = type(error).__name__.lower()
    return any(marker in error_name for marker in ("timeout", "rate", "temporar", "connection", "serviceunavailable"))


def _command_result(observation: dict[str, Any]) -> dict[str, Any] | None:
    result = observation.get("result")
    if not isinstance(result, dict):
        return None
    nested = result.get("result")
    if isinstance(nested, dict) and "exit_code" in nested:
        return nested
    if "exit_code" in result:
        return result
    return None
