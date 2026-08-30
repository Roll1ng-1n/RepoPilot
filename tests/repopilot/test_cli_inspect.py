from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from repopilot.artifacts import RunArtifacts
from repopilot.cli import create_app


def _make_metadata_run(tmp_path: Path) -> RunArtifacts:
    artifacts = RunArtifacts(tmp_path / "agent-runs", secrets=[])
    artifacts.write_metadata(
        {
            "run_id": artifacts.run_id,
            "status": "SUCCEEDED",
            "target_repository": "/tmp/example-repository",
            "model": "inspect-test-model",
            "plan": {
                "version": 1,
                "reason": "Initial Plan for this Agent Run.",
                "steps": [
                    {
                        "id": "complete-task",
                        "description": "Inspect the repository.",
                        "completion_condition": "The repository is inspected.",
                        "status": "COMPLETED",
                    }
                ],
            },
            "plan_history": [
                {
                    "version": 1,
                    "reason": "Initial Plan for this Agent Run.",
                    "steps": [
                        {
                            "id": "complete-task",
                            "description": "Inspect the repository.",
                            "completion_condition": "The repository is inspected.",
                            "status": "COMPLETED",
                        }
                    ],
                }
            ],
            "budget": {"max_steps": 30, "steps_used": 2},
            "recoveries": [{"action": "RETURN_OBSERVATION", "reason": "A command failed once."}],
            "context": {"strategy": "none"},
            "approval_context": {"environment": "local"},
            "verifications": [{"scope": "focused test", "reason": "Check the change.", "result": {"exit_code": 0}}],
            "git_commits": [],
        }
    )
    artifacts.append_trace(
        "run_started",
        task="Inspect the repository.",
        target_repository="/tmp/example-repository",
        model="inspect-test-model",
    )
    artifacts.append_trace("tool_call", tool_call_id="call-1", tool_name="list_files", arguments={"path": "."})
    artifacts.append_trace("run_finished", status="SUCCEEDED")
    artifacts.write_text("task_report.md", "# Task report\n")
    return artifacts


def _failing_model(_options: object) -> object:
    raise AssertionError("inspect must not construct a model")


def _failing_environment(_request: object) -> object:
    raise AssertionError("inspect must not construct an Environment")


def test_cli_inspect_renders_run_state_and_every_trace_event(tmp_path: Path) -> None:
    artifacts = _make_metadata_run(tmp_path)

    result = CliRunner().invoke(
        create_app(_failing_model, _failing_environment),
        ["inspect", artifacts.run_id, "--state-dir", str(tmp_path / "agent-runs")],
    )

    assert result.exit_code == 0, result.output
    assert f"Run ID: {artifacts.run_id}" in result.output
    assert "Status: SUCCEEDED" in result.output
    assert "Task: Inspect the repository." in result.output
    assert "Model: inspect-test-model" in result.output
    assert "Plan History:" in result.output
    assert "Recovery:" in result.output
    assert "Context:" in result.output
    assert "Approval:" in result.output
    assert "Task Verification:" in result.output
    assert "Git:" in result.output
    assert "Budget:" in result.output
    assert "run_started" in result.output
    assert "tool_call" in result.output
    assert "run_finished" in result.output
    assert "task_report.md" in result.output
    assert "# Task report" in result.output
    assert "checkpoint messages" not in result.output


def test_cli_inspect_json_is_single_normalized_document(tmp_path: Path) -> None:
    artifacts = _make_metadata_run(tmp_path)

    result = CliRunner().invoke(
        create_app(_failing_model, _failing_environment),
        ["inspect", artifacts.run_id, "--state-dir", str(tmp_path / "agent-runs"), "--json"],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["run_id"] == artifacts.run_id
    assert payload["status"] == "SUCCEEDED"
    assert payload["task"] == "Inspect the repository."
    assert payload["target_repository"] == "/tmp/example-repository"
    assert payload["model"] == "inspect-test-model"
    assert payload["state_source"] == "metadata"
    assert [event["type"] for event in payload["trace"]] == ["run_started", "tool_call", "run_finished"]
    assert payload["artifacts"]["task_report.md"]["available"] is True
    assert payload["task_report"] == "# Task report\n"
    assert payload["artifacts"]["checkpoint.json"]["available"] is False
    assert "messages" not in payload


def test_cli_inspect_is_read_only_and_does_not_call_composition_factories(tmp_path: Path) -> None:
    artifacts = _make_metadata_run(tmp_path)
    run_directory = artifacts.path
    before = {path.name: path.read_bytes() for path in run_directory.iterdir() if path.is_file()}

    result = CliRunner().invoke(
        create_app(_failing_model, _failing_environment),
        ["inspect", artifacts.run_id, "--state-dir", str(tmp_path / "agent-runs"), "--json"],
    )

    assert result.exit_code == 0, result.output
    after = {path.name: path.read_bytes() for path in run_directory.iterdir() if path.is_file()}
    assert after == before


def test_cli_inspect_reports_a_missing_run(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        create_app(_failing_model, _failing_environment),
        ["inspect", "missing-run", "--state-dir", str(tmp_path / "agent-runs")],
    )

    assert result.exit_code == 1
    assert "No persisted Agent Run exists for missing-run" in result.output


def test_cli_inspect_falls_back_to_checkpoint_without_dumping_messages(tmp_path: Path) -> None:
    artifacts = RunArtifacts(tmp_path / "agent-runs", secrets=[])
    artifacts.write_checkpoint(
        {
            "schema_version": 1,
            "run_id": artifacts.run_id,
            "status": "STOPPED",
            "task": "Resume the stopped inspection.",
            "model": {"model_name": "checkpoint-model"},
            "plan": {"version": 1, "reason": "Checkpoint plan.", "steps": []},
            "plan_history": [],
            "budget": {"steps_used": 1},
            "recovery": {"consecutive_failures": 0},
            "recoveries": [],
            "context": {"strategy": "sliding_window"},
            "approval_context": {"environment": "local"},
            "approval_request": None,
            "verifications": [],
            "repository": {"resolved_target_repository": "/tmp/checkpoint-repository"},
            "messages": [{"role": "user", "content": "secret checkpoint message"}],
        }
    )
    artifacts.append_trace("run_stopped", reason="KeyboardInterrupt")

    result = CliRunner().invoke(
        create_app(_failing_model, _failing_environment),
        ["inspect", artifacts.run_id, "--state-dir", str(tmp_path / "agent-runs"), "--json"],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["state_source"] == "checkpoint"
    assert payload["status"] == "STOPPED"
    assert payload["task"] == "Resume the stopped inspection."
    assert payload["model"] == "checkpoint-model"
    assert payload["target_repository"] == "/tmp/checkpoint-repository"
    assert "secret checkpoint message" not in result.output


def test_cli_inspect_reports_corrupt_metadata(tmp_path: Path) -> None:
    artifacts = RunArtifacts(tmp_path / "agent-runs", secrets=[])
    (artifacts.path / "metadata.json").write_text("not json")

    result = CliRunner().invoke(
        create_app(_failing_model, _failing_environment),
        ["inspect", artifacts.run_id, "--state-dir", str(tmp_path / "agent-runs")],
    )

    assert result.exit_code == 1
    assert f"Agent Run {artifacts.run_id} has invalid Metadata" in result.output
