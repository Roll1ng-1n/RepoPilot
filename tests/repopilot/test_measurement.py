from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from repopilot.artifacts import RunArtifacts
from repopilot.cli import create_app
from repopilot.evaluation import evaluate, normalize_trace
from repopilot.measurement import TimeRecorder, timing_metrics
from repopilot.model import AssistantTurn, ToolCall


def test_nested_time_intervals_do_not_double_count_summary_or_checkpoint(tmp_path):
    artifacts = RunArtifacts(tmp_path, secrets=[])
    now = [0.0]
    timing = TimeRecorder(artifacts, clock=lambda: now[0])
    with timing.measure("active_run"):
        now[0] += 1
        with timing.measure("context_prepare"):
            now[0] += 2
            with timing.measure("summary", category="model"):
                now[0] += 5
        with timing.measure("tool_execute", category="tool", tool_call_id="edit"):
            now[0] += 3
        with timing.measure("checkpoint_write_sync"):
            now[0] += 4
    trace = artifacts.read_trace()
    metrics = timing_metrics(trace)
    assert metrics["active_seconds"] == 15
    assert metrics["tool_seconds"] == 3
    assert metrics["orchestration_seconds"] == 7
    assert metrics["operations"]["context_prepare"] == 7
    assert sum(e["exclusive_seconds"] for e in trace if e["type"] == "operation_finished") == 15


def test_interrupted_span_preserves_measurements_and_unfinished_span_is_partial(tmp_path):
    artifacts = RunArtifacts(tmp_path, secrets=[])
    with pytest.raises(KeyboardInterrupt), artifacts.timing.measure("active_run"):
        with artifacts.timing.measure("tool_execute", category="tool"):
            raise KeyboardInterrupt
    assert timing_metrics(artifacts.read_trace())["coverage"] == "complete"
    artifacts.append_trace("operation_started", span_id="killed", operation="active_run")
    metrics = timing_metrics(artifacts.read_trace())
    assert metrics["coverage"] == "partial"
    assert metrics["active_seconds"] is None
    assert metrics["orchestration_seconds"] is None
    assert metrics["tool_seconds"] is not None
    assert timing_metrics([])["tool_seconds"] is None


def test_cli_records_shell_source_change_but_not_a_noop_and_inspect_reads_metrics(tmp_path):
    target = tmp_path / "target"
    target.mkdir()
    (target / "module.py").write_text("value = 1\n")
    turns = iter(
        [
            AssistantTurn(
                tool_calls=[
                    ToolCall(
                        "noop",
                        "run_command",
                        {
                            "command": "python -c \"from pathlib import Path; p=Path('module.py'); p.write_text(p.read_text())\""
                        },
                    )
                ]
            ),
            AssistantTurn(
                tool_calls=[
                    ToolCall(
                        "edit",
                        "run_command",
                        {
                            "command": "python -c \"from pathlib import Path; Path('module.py').write_text('value = 2\\n')\""
                        },
                    )
                ]
            ),
            AssistantTurn(
                tool_calls=[
                    ToolCall(
                        "verify",
                        "verify_task",
                        {
                            "command": "python -c 'import module; assert module.value == 2'",
                            "scope": "module",
                            "reason": "value is repaired",
                        },
                    )
                ]
            ),
            AssistantTurn(
                tool_calls=[
                    ToolCall("finish", "finish_task", {"root_cause": "old value", "changes": ["updated value"]})
                ]
            ),
        ]
    )

    class Model:
        model_name = "scripted"

        def complete(self, messages, tools):
            return next(turns)

    state = tmp_path / "runs"
    app = create_app(lambda _: Model())
    result = CliRunner().invoke(app, ["run", str(target), "--task", "repair value", "--state-dir", str(state)])
    assert result.exit_code == 0, result.output
    run = next(state.iterdir())
    events = RunArtifacts.reopen(state, run.name, secrets=[]).read_trace()
    evaluation = evaluate(True, "SUCCEEDED", {}, normalize_trace(events), [])
    assert evaluation["progress"]["first_effective_source_change_step"] == 2
    assert [e["tool_call_id"] for e in evaluation["progress"]["source_changes"]] == ["edit"]
    assert evaluation["duration"]["coverage"] == "complete"
    assert evaluation["duration"]["llm_seconds"] > 0
    inspection = CliRunner().invoke(app, ["inspect", run.name, "--state-dir", str(state), "--json"])
    assert inspection.exit_code == 0
    assert json.loads(inspection.stdout)["evaluation"]["duration"]["coverage"] == "complete"
