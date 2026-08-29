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
