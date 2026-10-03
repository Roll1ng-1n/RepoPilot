from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from repopilot.artifacts import RunArtifacts
from repopilot.cli import create_app
from repopilot.model import AssistantTurn, ToolCall
from repopilot.progress import ProgressTracker


def read(tracker, index, path, text="unchanged", **arguments):
    return tracker.observe(
        str(index), "read_file", {"path": path, **arguments}, {"ok": True, "result": {"stdout": text, "exit_code": 0}}
    )


@pytest.mark.parametrize("width", [1, 2, 3, 4])
def test_three_cycles_are_detected_once_and_survive_checkpoint(width):
    tracker = ProgressTracker()
    for i in range(width * 3 - 1):
        assert read(tracker, i, f"file-{i % width}")["diagnostic"] is None
    tracker = ProgressTracker.from_checkpoint(tracker.to_checkpoint())
    diagnosis = read(tracker, width * 3 - 1, f"file-{(width * 3 - 1) % width}")["diagnostic"]
    assert diagnosis["width"] == width
    assert len(diagnosis["calls"]) == width * 3
    for i in range(100):
        assert read(tracker, i, f"file-{i % width}")["diagnostic"] is None
    assert len(tracker.history) <= 12
    assert len(json.dumps(tracker.to_checkpoint())) < 20000


def test_distinct_ranges_pagination_queries_full_outputs_and_changes_do_not_loop():
    tracker = ProgressTracker()
    for i in range(20):
        assert read(tracker, i, "src/file.py", start_line=i + 1)["diagnostic"] is None
    for i in range(20):
        assert (
            tracker.observe(
                str(i),
                "search_code",
                {"query": f"term-{i}", "offset": i},
                {"ok": True, "result": {"stdout": "same preview", "full_artifact": f"object-{i}"}},
            )["diagnostic"]
            is None
        )
    read(tracker, 1, "src/file.py")
    read(tracker, 2, "./src/file.py")
    tracker.reset()
    assert read(tracker, 3, "src/file.py", "modified")["diagnostic"] is None
    assert read(tracker, 4, "src/file.py", "new result")["diagnostic"] is None
    assert tracker.observe("failed", "read_file", {}, {"ok": False}) is None
    assert tracker.observe("artifact", "read_artifact", {}, {"ok": True}) is None


def test_cli_loop_diagnostic_leads_to_a_verified_repair_and_disabled_switch_survives_resume(tmp_path):
    target = tmp_path / "target"
    target.mkdir()
    (target / "a.py").write_text("value = 1\n")
    (target / "b.py").write_text("other = 2\n")

    class Model:
        model_name = "scripted-loop"

        def __init__(self):
            self.step = 0

        def complete(self, messages, tools):
            self.step += 1
            if self.step <= 6:
                return AssistantTurn(
                    tool_calls=[
                        ToolCall(f"read-{self.step}", "read_file", {"path": "a.py" if self.step % 2 else "b.py"})
                    ]
                )
            if self.step == 7:
                assert "Repeated exploration cycle" in str(messages)
                return AssistantTurn(
                    tool_calls=[
                        ToolCall(
                            "edit",
                            "apply_patch",
                            {
                                "patch": "*** Begin Patch\n*** Update File: a.py\n@@\n-value = 1\n+value = 3\n*** End Patch"
                            },
                        )
                    ]
                )
            if self.step == 8:
                return AssistantTurn(
                    tool_calls=[
                        ToolCall(
                            "verify",
                            "verify_task",
                            {
                                "command": "python -c 'import a; assert a.value == 3'",
                                "scope": "value",
                                "reason": "repair",
                            },
                        )
                    ]
                )
            return AssistantTurn(
                tool_calls=[ToolCall("finish", "finish_task", {"root_cause": "value", "changes": ["repaired"]})]
            )

    state = tmp_path / "runs"
    model = Model()
    app = create_app(lambda _: model)
    result = CliRunner().invoke(app, ["run", str(target), "--task", "repair", "--state-dir", str(state)])
    assert result.exit_code == 0, result.output
    run_id = next(state.iterdir()).name
    artifacts = RunArtifacts.reopen(state, run_id, secrets=[])
    loops = [e for e in artifacts.read_trace() if e["type"] == "exploration_loop_detected"]
    assert len(loops) == 1
    assert [c["tool_call_id"] for c in loops[0]["calls"]] == [f"read-{i}" for i in range(1, 7)]
    assert [f["category"] for f in artifacts.read_checkpoint()["failures"]] == ["NO_PROGRESS"]

    class Repeating:
        model_name = "repeating"

        def complete(self, messages, tools):
            return AssistantTurn(tool_calls=[ToolCall(f"read-{len(messages)}", "read_file", {"path": "a.py"})])

    repeating_app = create_app(lambda _: Repeating())
    result = CliRunner().invoke(
        repeating_app,
        [
            "run",
            str(target),
            "--task",
            "explore",
            "--state-dir",
            str(tmp_path / "disabled"),
            "--no-progress-detection",
            "--max-steps",
            "3",
        ],
    )
    assert result.exit_code == 1 and "BUDGET_EXCEEDED" in result.output
    disabled_id = next((tmp_path / "disabled").iterdir()).name
    result = CliRunner().invoke(
        repeating_app, ["resume", disabled_id, "--state-dir", str(tmp_path / "disabled"), "--max-steps", "6"]
    )
    assert result.exit_code == 1 and "BUDGET_EXCEEDED" in result.output
    disabled = RunArtifacts.reopen(tmp_path / "disabled", disabled_id, secrets=[])
    assert disabled.read_checkpoint()["progress_tracker"]["enabled"] is False
    assert not any(e["type"] == "exploration_loop_detected" for e in disabled.read_trace())
