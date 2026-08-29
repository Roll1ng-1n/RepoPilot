import pytest

from repopilot.plan import PlanHistory, PlanInvariantError, PlanStep, PlanStepStatus


def _step(step_id: str, description: str) -> PlanStep:
    return PlanStep(
        id=step_id,
        description=description,
        completion_condition=f"{description} is complete.",
    )


@pytest.mark.parametrize("status", list(PlanStepStatus))
def test_plan_steps_support_every_declared_status(status: PlanStepStatus) -> None:
    plan_history = PlanHistory.for_task("Complete the task.")

    plan_history.update_step("complete-task", status)

    assert plan_history.current.steps[0].status is status


def test_plan_allows_at_most_one_in_progress_step() -> None:
    plan_history = PlanHistory.for_task("Complete the task.")
    plan_history.replan(
        [_step("inspect", "Inspect the code."), _step("implement", "Implement the code.")], "Split work."
    )
    plan_history.update_step("inspect", PlanStepStatus.IN_PROGRESS)

    with pytest.raises(PlanInvariantError, match="at most one IN_PROGRESS"):
        plan_history.update_step("implement", PlanStepStatus.IN_PROGRESS)


def test_replan_keeps_completed_steps_and_replaces_the_unfinished_portion() -> None:
    plan_history = PlanHistory.for_task("Complete the task.")
    plan_history.replan(
        [_step("inspect", "Inspect the code."), _step("implement", "Implement the original approach.")],
        "The task needs two steps.",
    )
    plan_history.update_step("inspect", PlanStepStatus.COMPLETED)

    plan_history.replan(
        [_step("implement-directly", "Implement the direct approach.")], "Inspection found a simpler path."
    )

    assert [plan.version for plan in plan_history.versions] == [1, 2, 3]
    assert plan_history.current.reason == "Inspection found a simpler path."
    assert [(step.id, step.status) for step in plan_history.current.steps] == [
        ("inspect", PlanStepStatus.COMPLETED),
        ("implement-directly", PlanStepStatus.PENDING),
    ]
    assert [step.id for step in plan_history.versions[1].steps] == ["inspect", "implement"]
    assert plan_history.versions[1].steps[0].status is PlanStepStatus.COMPLETED
