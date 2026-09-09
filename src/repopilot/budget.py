"""Configured limits and per-run accounting for bounded Agent Runs."""

from __future__ import annotations

import math
import time
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class RunBudget:
    """Limits that bound one Agent Run."""

    max_tokens: int | None = None
    max_cost_usd: float | None = None
    max_steps: int = 30
    max_replans: int = 2
    max_consecutive_failures: int = 3
    command_timeout_seconds: float = 300.0
    max_run_seconds: float | None = None

    def __post_init__(self) -> None:
        if self.max_tokens is not None and self.max_tokens < 1:
            raise ValueError("max_tokens must be positive.")
        if self.max_cost_usd is not None and (self.max_cost_usd <= 0 or not math.isfinite(self.max_cost_usd)):
            raise ValueError("max_cost_usd must be finite and positive.")
        if self.max_steps < 1:
            raise ValueError("max_steps must be at least 1.")
        if self.max_replans < 0:
            raise ValueError("max_replans must not be negative.")
        if self.max_consecutive_failures < 1:
            raise ValueError("max_consecutive_failures must be at least 1.")
        if self.command_timeout_seconds <= 0 or not math.isfinite(self.command_timeout_seconds):
            raise ValueError("command_timeout_seconds must be positive.")
        if self.max_run_seconds is not None and (self.max_run_seconds <= 0 or not math.isfinite(self.max_run_seconds)):
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
        self._elapsed_before_resume = 0.0
        self.requests_used = 0
        self.tokens_used = 0
        self.cost_used = 0.0
        self.unknown_tokens = False
        self.unknown_cost = False
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
            "max_tokens": self._budget.max_tokens,
            "max_cost_usd": self._budget.max_cost_usd,
            "requests_used": self.requests_used,
            "tokens_used": self.tokens_used,
            "cost_used": self.cost_used,
            "unknown_tokens": self.unknown_tokens,
            "unknown_cost": self.unknown_cost,
            "max_steps": self._budget.max_steps,
            "steps_used": self.steps_used,
            "max_replans": self._budget.max_replans,
            "replans_used": self.replans_used,
            "max_consecutive_failures": self._budget.max_consecutive_failures,
            "command_timeout_seconds": self._budget.command_timeout_seconds,
            "max_run_seconds": self._budget.max_run_seconds,
            "active_seconds_used": self._elapsed_before_resume + max(0.0, self._clock() - self._started_at),
        }

    @classmethod
    def from_snapshot(
        cls,
        budget: RunBudget,
        snapshot: dict[str, int | float],
        clock: Callable[[], float] = time.monotonic,
    ) -> RunBudgetTracker:
        """Resume the counters of one persisted Agent Run."""

        tracker = cls(budget, clock)
        try:
            steps_used = int(snapshot["steps_used"])
            replans_used = int(snapshot["replans_used"])
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("Checkpoint has invalid Run Budget counters.") from error
        if not 0 <= steps_used <= budget.max_steps:
            raise ValueError("Checkpoint has invalid used Agent Steps.")
        if not 0 <= replans_used <= budget.max_replans:
            raise ValueError("Checkpoint has invalid used Replans.")
        tracker.steps_used = steps_used
        tracker.replans_used = replans_used
        elapsed = float(snapshot.get("active_seconds_used", 0.0))
        if elapsed < 0 or not math.isfinite(elapsed):
            raise ValueError("Checkpoint has invalid active execution time.")
        tracker._elapsed_before_resume = elapsed
        for key in ("requests_used", "tokens_used", "cost_used", "unknown_tokens", "unknown_cost"):
            if key in snapshot:
                value = snapshot[key]
                if key in {"unknown_tokens", "unknown_cost"}:
                    valid = isinstance(value, bool)
                elif key in {"requests_used", "tokens_used"}:
                    valid = isinstance(value, int) and not isinstance(value, bool) and value >= 0
                else:
                    valid = (
                        isinstance(value, (int, float))
                        and not isinstance(value, bool)
                        and value >= 0
                        and math.isfinite(value)
                    )
                if not valid:
                    raise ValueError(f"Checkpoint has invalid {key}.")
                setattr(tracker, key, value)
        return tracker

    def remaining_seconds(self) -> float:
        if self._budget.max_run_seconds is None:
            return math.inf
        remaining = self._budget.max_run_seconds - self._elapsed_before_resume - (self._clock() - self._started_at)
        if remaining <= 0:
            raise BudgetExceeded("run_time")
        return remaining

    def _check_run_time(self) -> None:
        self.remaining_seconds()

    def before_request(self):
        self.remaining_seconds()
        if self._budget.max_tokens is not None:
            if self.unknown_tokens:
                raise BudgetExceeded("unknown_token_usage")
            if self.tokens_used >= self._budget.max_tokens:
                raise BudgetExceeded("tokens")
        if self._budget.max_cost_usd is not None:
            if self.unknown_cost:
                raise BudgetExceeded("unknown_cost")
            if self.cost_used >= self._budget.max_cost_usd:
                raise BudgetExceeded("cost")

    def record_request(self, usage, cost):
        self.requests_used += 1
        tokens = usage.get("total_tokens") if isinstance(usage, dict) else None
        if isinstance(tokens, int) and not isinstance(tokens, bool) and tokens >= 0:
            self.tokens_used += tokens
        else:
            self.unknown_tokens = True
        if isinstance(cost, (int, float)) and not isinstance(cost, bool) and math.isfinite(cost) and cost >= 0:
            self.cost_used += cost
        else:
            self.unknown_cost = True
