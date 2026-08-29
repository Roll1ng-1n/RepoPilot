import json
from pathlib import Path

from repopilot.artifacts import RunArtifacts
from repopilot.budget import RunBudget
from repopilot.environment import Command, CommandResult
from repopilot.model import AssistantTurn, ToolCall
from repopilot.plan import PlanHistory
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
