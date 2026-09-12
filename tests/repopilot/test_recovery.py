import json
from pathlib import Path

import pytest

from repopilot.artifacts import RunArtifacts
from repopilot.budget import RunBudget
from repopilot.environment import Command, CommandResult
from repopilot.model import AssistantTurn, ToolCall
from repopilot.plan import PlanHistory
from repopilot.recovery import FailureCategory, classify_tool_failure
from repopilot.runtime import AgentRuntime
from repopilot.tools import create_tool_registry


class ScriptedToolCallingModel:
    model_name = "scripted-tool-calling-model"

    def __init__(self, turns: list[AssistantTurn]):
        self._turns = iter(turns)

    def complete(self, messages: list[dict], tools: list[dict]) -> AssistantTurn:
        return next(self._turns)


class TimedOutEnvironment:
    """A non-local Environment double that reports structured command failure."""

    def __init__(self) -> None:
        self.commands: list[Command] = []

    def execute(self, command: Command) -> CommandResult:
        self.commands.append(command)
        return CommandResult(-1, "", "command timed out", 0.0, True)

    def close(self) -> None:
        pass


@pytest.mark.parametrize(
    "observation",
    [
        {
            "ok": True,
            "result": {
                "committed": False,
                "stage": {"exit_code": 1, "stdout": "", "stderr": "pathspec failed"},
            },
        },
        {
            "ok": True,
            "result": {
                "committed": False,
                "result": {"exit_code": 1, "stdout": "", "stderr": "nothing to commit"},
            },
        },
    ],
)
def test_classifies_failed_git_commit_as_a_tool_error(observation: dict) -> None:
    failure = classify_tool_failure("git_commit", observation)

    assert failure is not None
    assert failure.category is FailureCategory.TOOL_ERROR
    assert failure.tool_name == "git_commit"


def test_runtime_classifies_a_structured_environment_failure_without_inspecting_its_type(tmp_path: Path) -> None:
    target_repository = tmp_path / "target"
    target_repository.mkdir()
    state_directory = tmp_path / "agent-runs"
    artifacts = RunArtifacts(state_directory, secrets=[])
    environment = TimedOutEnvironment()
    plan_history = PlanHistory.for_task("Recover from an environment timeout.")
    model = ScriptedToolCallingModel(
        [
            AssistantTurn(tool_calls=[ToolCall("call-1", "run_command", {"command": "does-not-matter"})]),
            AssistantTurn(
                tool_calls=[
                    ToolCall(
                        "call-2",
                        "finish_task",
                        {"root_cause": "The environment timed out.", "changes": ["No change was needed."]},
                    )
                ]
            ),
        ]
    )

    result = AgentRuntime(
        model,
        create_tool_registry(environment, target_repository, plan_history, command_timeout_seconds=123.0),
        artifacts,
        plan_history,
        RunBudget(),
    ).run("Recover from an environment timeout.", target_repository)

    metadata = json.loads((result.artifact_directory / "metadata.json").read_text())

    assert result.status == "UNVERIFIED"
    assert environment.commands[0].timeout_seconds == 123.0
    assert metadata["failures"][0]["category"] == "ENVIRONMENT_ERROR"
    assert metadata["recoveries"][0]["action"] == "RETURN_OBSERVATION"


def test_transport_streak_is_independent_and_survives_checkpoint():
    from repopilot.recovery import Failure, RecoveryAction, RecoveryController

    recovery = RecoveryController(5)
    for _ in range(4):
        recovery.recover(Failure(FailureCategory.NO_PROGRESS, "blank"))
    timeout = Failure(FailureCategory.MODEL_ERROR, "timeout")
    assert recovery.recover(timeout, transient_model_error=True).action is RecoveryAction.RETRY_MODEL
    restored = RecoveryController(5)
    restored.restore(recovery.to_checkpoint(), [])
    assert restored.consecutive_failures == 4
    for _ in range(3):
        assert restored.recover(timeout, transient_model_error=True).action is RecoveryAction.RETRY_MODEL
    assert restored.recover(timeout, transient_model_error=True).action is RecoveryAction.STOP
    restored.record_model_success()
    assert restored.recover(timeout, transient_model_error=True).retry_delay_seconds == 0.25
    assert restored.recover(Failure(FailureCategory.MODEL_ERROR, "invalid credentials")).action is RecoveryAction.STOP


def test_legacy_recovery_checkpoint_keeps_only_actual_transport_streak():
    from repopilot.recovery import RecoveryController

    recovery = RecoveryController(5)
    recovery.restore({"consecutive_failures": 4}, [{"category": "NO_PROGRESS"}] * 4)
    assert recovery.to_checkpoint() == {"consecutive_failures": 4, "consecutive_model_failures": 0}
    recovery.restore({"consecutive_failures": 4}, [{"category": "NO_PROGRESS"}] * 2 + [{"category": "MODEL_ERROR"}] * 2)
    assert recovery.to_checkpoint() == {"consecutive_failures": 2, "consecutive_model_failures": 2}
    recovery.restore({"consecutive_failures": 0}, [{"category": "MODEL_ERROR"}] * 2)
    assert recovery.consecutive_model_failures == 0


def test_runtime_retries_first_timeout_after_no_progress_and_resets_on_response(tmp_path):
    from repopilot.environment import LocalExecutionEnvironment

    class Model:
        model_name = "mixed-recovery"
        calls = 0

        def complete(self, messages, tools):
            self.calls += 1
            if self.calls in {5, 7}:
                raise TimeoutError("temporary upstream delay")
            return AssistantTurn(content="")

    target = tmp_path / "target"
    target.mkdir()
    plan = PlanHistory.for_task("check")
    artifacts = RunArtifacts(tmp_path / "runs", secrets=[])
    delays = []
    result = AgentRuntime(
        Model(),
        create_tool_registry(LocalExecutionEnvironment(target), target, plan),
        artifacts,
        plan,
        RunBudget(max_steps=7, max_consecutive_failures=5),
        sleeper=delays.append,
    ).run("check", target)
    assert result.status == "BUDGET_EXCEEDED"
    assert delays == [0.25, 0.25]
    assert artifacts.read_checkpoint()["recovery"]["consecutive_model_failures"] == 1


def test_runtime_resume_does_not_grant_a_new_transport_retry_budget(tmp_path):
    from repopilot.environment import LocalExecutionEnvironment

    class Model:
        model_name = "unreachable-test-model"

        def complete(self, messages, tools):
            raise TimeoutError("upstream unreachable")

    target = tmp_path / "target"
    target.mkdir()
    artifacts = RunArtifacts(tmp_path / "runs", secrets=[])
    plan = PlanHistory.for_task("check")
    delays = []

    def runtime(steps):
        return AgentRuntime(
            Model(),
            create_tool_registry(LocalExecutionEnvironment(target), target, plan),
            artifacts,
            plan,
            RunBudget(max_steps=steps, max_consecutive_failures=3),
            sleeper=delays.append,
        )

    first = runtime(2).run("check", target)
    assert first.status == "BUDGET_EXCEEDED"
    checkpoint = artifacts.read_checkpoint()
    assert checkpoint["recovery"]["consecutive_model_failures"] == 2
    resumed = runtime(4).run("check", target, checkpoint=checkpoint)
    assert resumed.status == "FAILED"
    assert delays == [0.25, 0.5]
    assert artifacts.read_checkpoint()["budget"]["requests_used"] == 3


def test_no_recovery_ablation_preserves_independent_transport_retries():
    import importlib.util

    from repopilot.recovery import Failure, RecoveryAction, RecoveryController

    path = Path(__file__).resolve().parents[2] / "docs/evidence/issue24-effective-ablation/variants.py"
    spec = importlib.util.spec_from_file_location("historical_variants", path)
    variants = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(variants)
    recovery = RecoveryController(3)
    with variants.variant_context("no-recovery", None):
        for _ in range(4):
            assert recovery.recover(Failure(FailureCategory.NO_PROGRESS, "blank")).action is RecoveryAction.STOP
        assert (
            recovery.recover(Failure(FailureCategory.MODEL_ERROR, "timeout"), transient_model_error=True).action
            is RecoveryAction.RETRY_MODEL
        )
