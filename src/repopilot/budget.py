"""Configured limits and per-run accounting for bounded Agent Runs."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class RunBudget:
    """Limits that bound one Agent Run."""

    max_steps: int = 30
    max_replans: int = 2
    max_consecutive_failures: int = 3
    command_timeout_seconds: float = 300.0
    max_run_seconds: float = 30.0 * 60.0

    def __post_init__(self) -> None:
        if self.max_steps < 1:
            raise ValueError("max_steps must be at least 1.")
        if self.max_replans < 0:
            raise ValueError("max_replans must not be negative.")
        if self.max_consecutive_failures < 1:
            raise ValueError("max_consecutive_failures must be at least 1.")
        if self.command_timeout_seconds <= 0:
            raise ValueError("command_timeout_seconds must be positive.")
        if self.max_run_seconds <= 0:
            raise ValueError("max_run_seconds must be positive.")

    def start(self, clock: Callable[[], float] = time.monotonic) -> RunBudgetTracker:
        """Start accounting for a new Agent Run."""
        return RunBudgetTracker(self, clock)


class BudgetExceeded(Exception):
    """Raised before work that would exceed an Agent Run limit."""

    def __init__(self, limit: str):
        self.limit = limit
        super().__init__(f"Agent Run budget exhausted: {limit}.")


class RunBudgetTracker:
    """Mutable accounting kept private to one Agent Run."""

    def __init__(self, budget: RunBudget, clock: Callable[[], float]):
        self._budget = budget
        self._clock = clock
        self._started_at = clock()
        self.steps_used = 0
        self.replans_used = 0

    def consume_step(self) -> None:
        self._check_run_time()
        if self.steps_used >= self._budget.max_steps:
            raise BudgetExceeded("steps")
        self.steps_used += 1

    def consume_replan(self) -> None:
        self._check_run_time()
        if self.replans_used >= self._budget.max_replans:
            raise BudgetExceeded("replans")
        self.replans_used += 1

    def snapshot(self) -> dict[str, int | float]:
        """Return auditable configuration and consumption without wall-clock noise."""
        return {
            "max_steps": self._budget.max_steps,
            "steps_used": self.steps_used,
            "max_replans": self._budget.max_replans,
            "replans_used": self.replans_used,
            "max_consecutive_failures": self._budget.max_consecutive_failures,
            "command_timeout_seconds": self._budget.command_timeout_seconds,
            "max_run_seconds": self._budget.max_run_seconds,
        }

    def _check_run_time(self) -> None:
        if self._clock() - self._started_at >= self._budget.max_run_seconds:
            raise BudgetExceeded("run_time")
