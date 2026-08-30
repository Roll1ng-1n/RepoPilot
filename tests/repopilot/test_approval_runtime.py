"""Human Approval lifecycle at the CLI seam."""

from __future__ import annotations

import json
import subprocess
from copy import deepcopy
from pathlib import Path

from typer.testing import CliRunner

from repopilot.cli import create_app
from repopilot.environment import LocalExecutionEnvironment
from repopilot.model import AssistantTurn, ToolCall


class ScriptedToolCallingModel:
    model_name = "scripted-tool-calling-model"

    def __init__(self, turns: list[AssistantTurn]):
        self._turns = iter(turns)
        self.requests: list[tuple[list[dict], list[dict]]] = []

    def complete(self, messages: list[dict], tools: list[dict]) -> AssistantTurn:
        self.requests.append((deepcopy(messages), tools))
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


def _patch() -> str:
    return """\\
diff --git a/README.md b/README.md
--- a/README.md
+++ b/README.md
@@ -1 +1 @@
-RepoPilot needle
+RepoPilot approved change
"""


def _finish_turn() -> AssistantTurn:
    return AssistantTurn(
        tool_calls=[
            ToolCall(
                "finish",
                "finish_task",
                {
                    "root_cause": "The README required an approved revision.",
                    "changes": ["Updated the README."],
                    "risks": ["The local Git Commit records the verified work."],
                },
            )
        ]
    )


def test_cli_approval_executes_the_snapshot_then_resumes_and_reports_the_commit(tmp_path: Path) -> None:
    target_repository = tmp_path / "target"
    _make_target_repository(target_repository)
    state_directory = tmp_path / "agent-runs"
    waiting_model = ScriptedToolCallingModel(
        [
            AssistantTurn(tool_calls=[ToolCall("patch", "apply_patch", {"patch": _patch()})]),
            AssistantTurn(
                tool_calls=[
                    ToolCall(
                        "commit",
                        "git_commit",
                        {
                            "message": "Record the approved README revision",
                            "reason": "Preserve the requested README change in local history.",
                            "paths": ["README.md"],
                        },
                    )
                ]
            ),
        ]
    )

    waiting = CliRunner().invoke(
        create_app(lambda _: waiting_model),
        ["run", str(target_repository), "--task", "Update and commit the README.", "--state-dir", str(state_directory)],
    )

    assert waiting.exit_code == 0, waiting.output
    assert "WAITING_FOR_APPROVAL" in waiting.output
    run_directory = next(state_directory.iterdir())
    checkpoint = json.loads((run_directory / "checkpoint.json").read_text())
    assert checkpoint["status"] == "WAITING_FOR_APPROVAL"
    assert checkpoint["approval_request"] == {
        "tool_call": {
            "id": "commit",
            "name": "git_commit",
            "arguments": {
                "message": "Record the approved README revision",
                "reason": "Preserve the requested README change in local history.",
                "paths": ["README.md"],
            },
        },
        "reason": "Creating a local Git Commit writes Target Repository history.",
    }
    assert (
        subprocess.run(
            ["git", "rev-list", "--count", "HEAD"], cwd=target_repository, capture_output=True, check=True, text=True
        ).stdout
        == "1\n"
    )

    resumed_model = ScriptedToolCallingModel([_finish_turn()])
    approved = CliRunner().invoke(
        create_app(lambda _: resumed_model),
        ["approve", run_directory.name, "--state-dir", str(state_directory)],
    )

    assert approved.exit_code == 0, approved.output
    metadata = json.loads((run_directory / "metadata.json").read_text())
    commit_hash = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=target_repository, capture_output=True, check=True, text=True
    ).stdout.strip()
    report = (run_directory / "task_report.md").read_text()
    events = [json.loads(line) for line in (run_directory / "trace.jsonl").read_text().splitlines()]
    assert metadata["status"] == "UNVERIFIED"
    assert metadata["git_commits"] == [
        {
            "commit_hash": commit_hash,
            "message": "Record the approved README revision",
            "paths": ["README.md"],
            "reason": "Preserve the requested README change in local history.",
        }
    ]
    assert f"- `{commit_hash}`: Preserve the requested README change in local history." in report
    assert {event["type"] for event in events} >= {"approval_requested", "approval_granted", "git_commit"}


def test_cli_rejection_returns_a_tool_observation_to_the_resumed_model(tmp_path: Path) -> None:
    target_repository = tmp_path / "target"
    _make_target_repository(target_repository)
    state_directory = tmp_path / "agent-runs"
    waiting_model = ScriptedToolCallingModel(
        [
            AssistantTurn(
                tool_calls=[
                    ToolCall(
                        "commit",
                        "git_commit",
                        {"message": "Record work", "reason": "Keep a local history.", "paths": ["README.md"]},
                    )
                ]
            )
        ]
    )
    waiting = CliRunner().invoke(
        create_app(lambda _: waiting_model),
        ["run", str(target_repository), "--task", "Commit the README.", "--state-dir", str(state_directory)],
    )
    assert waiting.exit_code == 0, waiting.output
    run_directory = next(state_directory.iterdir())

    resumed_model = ScriptedToolCallingModel([_finish_turn()])
    rejected = CliRunner().invoke(
        create_app(lambda _: resumed_model),
        ["reject", run_directory.name, "--state-dir", str(state_directory)],
    )

    assert rejected.exit_code == 0, rejected.output
    first_request_messages = resumed_model.requests[0][0]
    rejection = next(message for message in first_request_messages if message.get("tool_call_id") == "commit")
    assert json.loads(rejection["content"]) == {
        "details": "Human Approval rejected the Tool Call.",
        "error": "approval_rejected",
        "ok": False,
    }
    assert (
        subprocess.run(
            ["git", "rev-list", "--count", "HEAD"], cwd=target_repository, capture_output=True, check=True, text=True
        ).stdout
        == "1\n"
    )


def test_cli_resumes_remaining_tool_calls_from_the_same_assistant_turn_after_approval(tmp_path: Path) -> None:
    target_repository = tmp_path / "target"
    _make_target_repository(target_repository)
    state_directory = tmp_path / "agent-runs"
    waiting_model = ScriptedToolCallingModel(
        [
            AssistantTurn(
                tool_calls=[
                    ToolCall("patch", "apply_patch", {"patch": _patch()}),
                    ToolCall(
                        "commit",
                        "git_commit",
                        {"message": "Record work", "reason": "Keep local history.", "paths": ["README.md"]},
                    ),
                    ToolCall("diff", "view_diff", {}),
                ]
            )
        ]
    )
    waiting = CliRunner().invoke(
        create_app(lambda _: waiting_model),
        ["run", str(target_repository), "--task", "Update and commit the README.", "--state-dir", str(state_directory)],
    )
    assert waiting.exit_code == 0, waiting.output
    run_directory = next(state_directory.iterdir())
    checkpoint = json.loads((run_directory / "checkpoint.json").read_text())
    assert checkpoint["pending_tool_calls"] == [{"id": "diff", "name": "view_diff", "arguments": {}}]

    resumed_model = ScriptedToolCallingModel([_finish_turn()])
    approved = CliRunner().invoke(
        create_app(lambda _: resumed_model),
        ["approve", run_directory.name, "--state-dir", str(state_directory)],
    )

    assert approved.exit_code == 0, approved.output
    metadata = json.loads((run_directory / "metadata.json").read_text())
    assert [item["tool_call_id"] for item in metadata["tool_results"]] == ["patch", "commit", "diff", "finish"]
    resumed_messages = resumed_model.requests[0][0]
    assert [message["tool_call_id"] for message in resumed_messages if message["role"] == "tool"] == [
        "patch",
        "commit",
        "diff",
    ]


def test_cli_auto_approves_only_an_explicit_disposable_docker_benchmark(tmp_path: Path) -> None:
    target_repository = tmp_path / "target"
    _make_target_repository(target_repository)
    state_directory = tmp_path / "agent-runs"
    model = ScriptedToolCallingModel(
        [
            AssistantTurn(tool_calls=[ToolCall("patch", "apply_patch", {"patch": _patch()})]),
            AssistantTurn(
                tool_calls=[
                    ToolCall(
                        "commit",
                        "git_commit",
                        {"message": "Record work", "reason": "Keep local history.", "paths": ["README.md"]},
                    )
                ]
            ),
            _finish_turn(),
        ]
    )

    result = CliRunner().invoke(
        create_app(lambda _: model, lambda request: LocalExecutionEnvironment(request.target_repository)),
        [
            "run",
            str(target_repository),
            "--task",
            "Update and commit the README.",
            "--state-dir",
            str(state_directory),
            "--environment",
            "docker",
            "--image",
            "disposable-benchmark-image",
            "--auto-approve-disposable-docker-benchmark",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "WAITING_FOR_APPROVAL" not in result.output
    run_directory = next(state_directory.iterdir())
    events = [json.loads(line) for line in (run_directory / "trace.jsonl").read_text().splitlines()]
    assert any(event["type"] == "approval_auto_approved" for event in events)


def test_cli_rejects_automatic_approval_for_the_local_environment(tmp_path: Path) -> None:
    target_repository = tmp_path / "target"
    _make_target_repository(target_repository)

    result = CliRunner().invoke(
        create_app(lambda _: (_ for _ in ()).throw(AssertionError("Model factory must not run."))),
        [
            "run",
            str(target_repository),
            "--task",
            "Inspect the repository.",
            "--auto-approve-disposable-docker-benchmark",
        ],
    )

    assert result.exit_code == 2
    assert "only for an explicitly disposable Docker benchmark" in result.output
