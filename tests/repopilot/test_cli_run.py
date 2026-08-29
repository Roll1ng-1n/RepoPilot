import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from repopilot.cli import create_app
from repopilot.environment import (
    Command,
    CommandResult,
    EnvironmentCreationError,
    EnvironmentRequest,
    ExecutionEnvironment,
)
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
    subprocess.run(["git", "add", "README.md"], cwd=path, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=RepoPilot Runtime Test",
            "-c",
            "user.email=runtime-test@example.invalid",
            "commit",
            "--quiet",
            "-m",
            "Initial Target Repository state",
        ],
        cwd=path,
        check=True,
    )


def _docker_available() -> bool:
    executable = shutil.which("docker")
    if executable is None:
        return False
    try:
        subprocess.run([executable, "version"], capture_output=True, check=True, timeout=5)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return False
    return True


@pytest.mark.parametrize(
    ("environment", "environment_arguments"),
    [
        ("local", []),
        pytest.param(
            "docker",
            ["--image", os.environ.get("REPOPILOT_DOCKER_TEST_IMAGE", "python:3.12-bookworm")],
            marks=pytest.mark.skipif(not _docker_available(), reason="Docker is unavailable"),
        ),
    ],
)
def test_cli_completes_a_verified_patch_run_and_persists_its_evidence(
    tmp_path: Path, environment: str, environment_arguments: list[str]
) -> None:
    target_repository = tmp_path / "target"
    _make_target_repository(target_repository)
    state_directory = tmp_path / "agent-runs"
    patch = """\\
diff --git a/README.md b/README.md
--- a/README.md
+++ b/README.md
@@ -1 +1 @@
-RepoPilot needle
+RepoPilot verified change
"""
    verification_command = (
        "python -c \"from pathlib import Path; assert Path('README.md').read_text() == 'RepoPilot verified change\\n'\""
    )
    model = ScriptedToolCallingModel(
        [
            AssistantTurn(tool_calls=[ToolCall("call-1", "apply_patch", {"patch": patch})]),
            AssistantTurn(tool_calls=[ToolCall("call-2", "view_diff", {})]),
            AssistantTurn(
                tool_calls=[
                    ToolCall(
                        "call-3",
                        "verify_task",
                        {
                            "command": verification_command,
                            "scope": "README.md patch",
                            "reason": "Proves the requested repository change is present.",
                        },
                    )
                ]
            ),
            AssistantTurn(
                tool_calls=[
                    ToolCall(
                        "call-4",
                        "finish_task",
                        {
                            "root_cause": "The README still contained the obsolete text.",
                            "changes": ["Replaced the obsolete README text."],
                            "risks": ["No runtime behavior changed."],
                        },
                    )
                ]
            ),
        ]
    )

    result = CliRunner().invoke(
        create_app(lambda _: model),
        [
            "run",
            str(target_repository),
            "--task",
            "Replace the obsolete README text and verify it.",
            "--state-dir",
            str(state_directory),
            "--environment",
            environment,
            *environment_arguments,
        ],
    )

    assert result.exit_code == 0, result.output
    assert "SUCCEEDED" in result.output
    if environment == "local":
        assert "Local Environment executes commands directly in the Target Repository." in result.output
    else:
        assert "not a security boundary" in result.output
    assert (target_repository / "README.md").read_text() == "RepoPilot verified change\n"

    run_directory = next(state_directory.iterdir())
    metadata = json.loads((run_directory / "metadata.json").read_text())
    events = [json.loads(line) for line in (run_directory / "trace.jsonl").read_text().splitlines()]
    verification = json.loads((run_directory / "verification.json").read_text())
    report = (run_directory / "task_report.md").read_text()

    assert metadata["status"] == "SUCCEEDED"
    assert "-RepoPilot needle" in (run_directory / "patch.diff").read_text()
    assert verification["verifications"][0]["command"] == verification_command
    assert verification["verifications"][0]["scope"] == "README.md patch"
    assert verification["verifications"][0]["reason"] == "Proves the requested repository change is present."
    assert verification["verifications"][0]["result"]["exit_code"] == 0
    assert "## Root cause\n\nThe README still contained the obsolete text." in report
    assert "## Changes\n\n- Replaced the obsolete README text." in report
    assert (
        "## Verification\n\n- `README.md patch`: Proves the requested repository change is present. (passed)" in report
    )
    assert "## Risks\n\n- No runtime behavior changed." in report
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
        "run_finished",
    ]
    assert [event["tool_name"] for event in events if event["type"] == "tool_call"] == [
        "apply_patch",
        "view_diff",
        "verify_task",
        "finish_task",
    ]
    assert events[2]["arguments"]["patch"] == patch
    assert events[3]["observation"]["result"]["applied"] is True
    assert "-RepoPilot needle" in events[5]["observation"]["result"]["patch"]
    assert {schema["function"]["name"] for schema in model.requests[0][1]} >= {
        "apply_patch",
        "view_diff",
        "verify_task",
        "finish_task",
    }


def test_cli_selects_an_environment_through_the_factory(tmp_path: Path) -> None:
    target_repository = tmp_path / "target"
    _make_target_repository(target_repository)
    requests: list[EnvironmentRequest] = []

    class RecordingEnvironment:
        closed = False

        def execute(self, _command: Command) -> CommandResult:
            return CommandResult(0, "", "", 0.0, False)

        def close(self) -> None:
            self.closed = True

    environment = RecordingEnvironment()
    model = ScriptedToolCallingModel(
        [
            AssistantTurn(
                tool_calls=[
                    ToolCall(
                        "call-1",
                        "finish_task",
                        {
                            "root_cause": "No changes were needed.",
                            "changes": ["No repository changes were made."],
                            "risks": ["No verification evidence was collected."],
                        },
                    )
                ]
            )
        ]
    )

    def environment_factory(request: EnvironmentRequest) -> RecordingEnvironment:
        requests.append(request)
        return environment

    result = CliRunner().invoke(
        create_app(lambda _: model, environment_factory),
        [
            "run",
            str(target_repository),
            "--task",
            "Inspect the repository.",
            "--state-dir",
            str(tmp_path / "agent-runs"),
            "--environment",
            "docker",
            "--image",
            "repo-image",
        ],
    )

    assert result.exit_code == 0, result.output
    assert requests == [
        EnvironmentRequest(target_repository=target_repository.resolve(), environment="docker", image="repo-image")
    ]
    assert environment.closed is True


def test_cli_rejects_docker_without_an_image(tmp_path: Path) -> None:
    target_repository = tmp_path / "target"
    _make_target_repository(target_repository)
    model = ScriptedToolCallingModel([])

    result = CliRunner().invoke(
        create_app(lambda _: model),
        ["run", str(target_repository), "--task", "Inspect the repository.", "--environment", "docker"],
    )

    assert result.exit_code == 2
    assert "requires an image" in result.output


def test_cli_reports_an_unavailable_docker_environment_without_falling_back_to_local(tmp_path: Path) -> None:
    target_repository = tmp_path / "target"
    _make_target_repository(target_repository)
    model = ScriptedToolCallingModel([])

    def unavailable_environment(_request: EnvironmentRequest) -> ExecutionEnvironment:
        raise EnvironmentCreationError("Unable to start Docker Environment: docker is unavailable")

    result = CliRunner().invoke(
        create_app(lambda _: model, unavailable_environment),
        [
            "run",
            str(target_repository),
            "--task",
            "Inspect the repository.",
            "--environment",
            "docker",
            "--image",
            "repo-image",
        ],
    )

    assert result.exit_code == 1
    assert "docker is unavailable" in result.output
    assert "Local Environment executes commands" not in result.output


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
            AssistantTurn(
                tool_calls=[
                    ToolCall(
                        "call-5",
                        "finish_task",
                        {
                            "root_cause": "The task was exploration only.",
                            "changes": ["No repository changes were needed."],
                            "risks": ["No verification evidence was collected."],
                        },
                    )
                ]
            ),
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
    assert (run_directories[0] / "patch.diff").read_text() == ""
    assert json.loads((run_directories[0] / "verification.json").read_text()) == {"verifications": []}
    assert "No verification evidence was collected." in (run_directories[0] / "task_report.md").read_text()
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
        "apply_patch",
        "view_diff",
        "verify_task",
        "finish_task",
        "update_plan",
        "replan",
    }


def test_cli_prompts_for_a_task_when_the_task_option_is_omitted(tmp_path: Path) -> None:
    target_repository = tmp_path / "target"
    _make_target_repository(target_repository)
    model = ScriptedToolCallingModel(
        [
            AssistantTurn(
                tool_calls=[
                    ToolCall(
                        "call-1",
                        "finish_task",
                        {
                            "root_cause": "No changes were needed.",
                            "changes": ["No repository changes were made."],
                            "risks": ["No verification evidence was collected."],
                        },
                    )
                ]
            )
        ]
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
            AssistantTurn(
                tool_calls=[
                    ToolCall(
                        "call-6",
                        "finish_task",
                        {
                            "root_cause": "The test exercises Plan and Replan behavior.",
                            "changes": ["Completed the explicit Plan without repository changes."],
                            "risks": ["No Task Verification evidence was collected."],
                        },
                    )
                ]
            ),
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
