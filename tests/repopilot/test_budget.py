import pytest

from repopilot.budget import BudgetExceeded, RunBudget


def test_run_budget_stops_before_an_extra_agent_step() -> None:
    budget = RunBudget(max_steps=1)
    tracker = budget.start(clock=lambda: 0.0)

    tracker.consume_step()

    with pytest.raises(BudgetExceeded, match="steps"):
        tracker.consume_step()

    assert tracker.snapshot()["steps_used"] == 1


def test_run_budget_stops_when_the_agent_run_time_is_exhausted() -> None:
    times = iter([0.0, 1.0])
    budget = RunBudget(max_run_seconds=0.5)
    tracker = budget.start(clock=lambda: next(times))

    with pytest.raises(BudgetExceeded, match="run_time"):
        tracker.consume_step()

    assert tracker.snapshot()["steps_used"] == 0
