import json
import subprocess
from pathlib import Path

from typer.testing import CliRunner

from repopilot.cli import create_app
from repopilot.model import AssistantTurn, ToolCall


class ScriptedToolCallingModel:
    """A model-boundary fake for a complete CLI Agent Run."""

    model_name = "scripted-tool-calling-model"

    def __init__(self, turns: list[AssistantTurn]):
        self._turns = iter(turns)
        self.requests: list[tuple[list[dict], list[dict]]] = []

    def complete(self, messages: list[dict], tools: list[dict]) -> AssistantTurn:
        self.requests.append((messages, tools))
        return next(self._turns)


def _make_target_repository(path: Path) -> None:
    path.mkdir()
    (path / "README.md").write_text("RepoPilot needle\n")
    subprocess.run(["git", "init", "--quiet"], cwd=path, check=True)


def test_cli_runs_a_read_only_native_tool_calling_agent_and_writes_safe_artifacts(tmp_path: Path) -> None:
    target_repository = tmp_path / "target"
    _make_target_repository(target_repository)
    state_directory = tmp_path / "agent-runs"
    before_status = subprocess.run(
        ["git", "status", "--short"], cwd=target_repository, capture_output=True, check=True, text=True
    ).stdout
    model = ScriptedToolCallingModel(
        [
            AssistantTurn(tool_calls=[ToolCall("call-1", "list_files", {"path": "."})]),
            AssistantTurn(tool_calls=[ToolCall("call-2", "search_code", {"query": "needle", "path": "."})]),
            AssistantTurn(tool_calls=[ToolCall("call-3", "read_file", {"path": "README.md"})]),
            AssistantTurn(tool_calls=[ToolCall("call-4", "run_command", {"command": "git status --short"})]),
            AssistantTurn(tool_calls=[ToolCall("call-5", "finish_task", {"summary": "Exploration complete."})]),
        ]
    )
    app = create_app(lambda _: model)

    result = CliRunner().invoke(
        app,
        [
            "run",
            str(target_repository),
            "--task",
            "Explore this repository without modifying it.",
            "--state-dir",
            str(state_directory),
            "--api-key",
            "test-api-key",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Local Environment executes commands directly in the Target Repository." in result.output
    assert "UNVERIFIED" in result.output
    assert (
        subprocess.run(
            ["git", "status", "--short"], cwd=target_repository, capture_output=True, check=True, text=True
        ).stdout
        == before_status
    )
    assert not (target_repository / ".repopilot").exists()

    run_directories = list(state_directory.iterdir())
    assert len(run_directories) == 1
    metadata = json.loads((run_directories[0] / "metadata.json").read_text())
    events = [json.loads(line) for line in (run_directories[0] / "trace.jsonl").read_text().splitlines()]
    persisted_artifacts = json.dumps({"metadata": metadata, "events": events})

    assert metadata["status"] == "UNVERIFIED"
    assert [event["type"] for event in events] == [
        "run_started",
        "plan_created",
        "tool_call",
        "tool_result",
        "tool_call",
        "tool_result",
        "tool_call",
        "tool_result",
        "tool_call",
        "tool_result",
        "tool_call",
        "tool_result",
        "run_finished",
    ]
    assert "test-api-key" not in persisted_artifacts
    assert {schema["function"]["name"] for schema in model.requests[0][1]} == {
        "list_files",
        "search_code",
        "read_file",
        "run_command",
        "finish_task",
        "update_plan",
        "replan",
    }


def test_cli_prompts_for_a_task_when_the_task_option_is_omitted(tmp_path: Path) -> None:
    target_repository = tmp_path / "target"
    _make_target_repository(target_repository)
    model = ScriptedToolCallingModel(
        [AssistantTurn(tool_calls=[ToolCall("call-1", "finish_task", {"summary": "No changes needed."})])]
    )

    result = CliRunner().invoke(
        create_app(lambda _: model),
        ["run", str(target_repository), "--state-dir", str(tmp_path / "agent-runs")],
        input="Inspect the repository.\n",
    )

    assert result.exit_code == 0, result.output
    assert model.requests[0][0][1]["content"] == "Inspect the repository."


def test_cli_records_a_versioned_plan_and_replan_from_agent_control_tools(tmp_path: Path) -> None:
    target_repository = tmp_path / "target"
    _make_target_repository(target_repository)
    state_directory = tmp_path / "agent-runs"
    model = ScriptedToolCallingModel(
        [
            AssistantTurn(
                tool_calls=[
                    ToolCall(
                        "call-1",
                        "replan",
                        {
                            "reason": "The repository needs inspection before implementation.",
                            "steps": [
                                {
                                    "id": "inspect",
                                    "description": "Inspect the repository structure.",
                                    "completion_condition": "Relevant files are identified.",
                                },
                                {
                                    "id": "implement",
                                    "description": "Implement the requested change.",
                                    "completion_condition": "The change is verified.",
                                },
                            ],
                        },
                    )
                ]
            ),
            AssistantTurn(
                tool_calls=[ToolCall("call-2", "update_plan", {"step_id": "inspect", "status": "IN_PROGRESS"})]
            ),
            AssistantTurn(
                tool_calls=[ToolCall("call-3", "update_plan", {"step_id": "inspect", "status": "COMPLETED"})]
            ),
            AssistantTurn(
                tool_calls=[
                    ToolCall(
                        "call-4",
                        "replan",
                        {
                            "reason": "Inspection found a more direct implementation path.",
                            "steps": [
                                {
                                    "id": "implement-directly",
                                    "description": "Implement the direct change.",
                                    "completion_condition": "The focused Runtime Test passes.",
                                }
                            ],
                        },
                    )
                ]
            ),
            AssistantTurn(
                tool_calls=[ToolCall("call-5", "update_plan", {"step_id": "implement-directly", "status": "COMPLETED"})]
            ),
            AssistantTurn(tool_calls=[ToolCall("call-6", "finish_task", {"summary": "Completed the plan."})]),
        ]
    )

    result = CliRunner().invoke(
        create_app(lambda _: model),
        [
            "run",
            str(target_repository),
            "--task",
            "Implement a verified change.",
            "--state-dir",
            str(state_directory),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Plan v3" in result.output
    assert "[COMPLETED] Inspect the repository structure." in result.output
    assert "[COMPLETED] Implement the direct change." in result.output
    assert "Current Plan:" in model.requests[0][0][0]["content"]

    run_directory = next(state_directory.iterdir())
    metadata = json.loads((run_directory / "metadata.json").read_text())
    events = [json.loads(line) for line in (run_directory / "trace.jsonl").read_text().splitlines()]

    assert [plan["version"] for plan in metadata["plan_history"]] == [1, 2, 3]
    assert metadata["plan_history"][2]["steps"] == [
        {
            "id": "inspect",
            "description": "Inspect the repository structure.",
            "completion_condition": "Relevant files are identified.",
            "status": "COMPLETED",
        },
        {
            "id": "implement-directly",
            "description": "Implement the direct change.",
            "completion_condition": "The focused Runtime Test passes.",
            "status": "COMPLETED",
        },
    ]
    assert [event["type"] for event in events if event["type"].startswith("plan_")] == [
        "plan_created",
        "plan_replanned",
        "plan_updated",
        "plan_updated",
        "plan_replanned",
        "plan_updated",
    ]
    assert events[-1] == {"type": "run_finished", "status": "UNVERIFIED"}
