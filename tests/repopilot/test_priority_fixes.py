"""End-to-end regressions for follow-up issues #25 and #26."""

from __future__ import annotations

import hashlib
import json
import math

import pytest
from typer.testing import CliRunner

from repopilot.artifacts import RunArtifacts
from repopilot.benchmark import _copy_runtime_artifacts, capture_patch
from repopilot.budget import RunBudget, RunBudgetTracker
from repopilot.cli import create_app
from repopilot.environment import LocalExecutionEnvironment
from repopilot.model import AssistantTurn, ToolCall
from repopilot.plan import PlanHistory
from repopilot.runtime import AgentRuntime
from repopilot.tools import create_tool_registry
from tests.repopilot.test_issue_regressions import target  # noqa: F401


def registry(root, required=()):
    return create_tool_registry(
        LocalExecutionEnvironment(root), root, PlanHistory.for_task("Check"), required_verifications=required
    )


def verify(reg, command="true", scope="check", **extra):
    return reg.dispatch(
        ToolCall("verify", "verify_task", {"command": command, "scope": scope, "reason": "regression", **extra})
    )["result"]


def finish(reg):
    return reg.dispatch(ToolCall("finish", "finish_task", {"root_cause": "checked", "changes": ["checked"]}))["result"]


def test_generated_cache_does_not_invalidate_source_but_source_writes_do(target):
    (target / "module.py").write_text("VALUE = 1\n")
    reg = registry(target)
    check = verify(reg, 'env -u PYTHONDONTWRITEBYTECODE python -c "import module; assert module.VALUE == 1"')
    assert list(target.glob("__pycache__/*.pyc"))
    assert check["before_fingerprint"] == check["after_fingerprint"]
    assert finish(reg)["status"] == "SUCCEEDED"
    verify(reg, "echo changed > file.txt")
    assert not finish(reg)["completion_allowed"]


def test_scope_rename_reuses_command_identity(target):
    reg = registry(target)
    verify(reg, "test -f ready", "initial description")
    (target / "ready").touch()
    verify(reg, "test -f ready", "final description")
    assert finish(reg)["status"] == "SUCCEEDED"


def test_explicit_check_ids_keep_same_scope_independent_and_allow_retries(target):
    reg = registry(target)
    verify(reg, "false", check_id="unit")
    verify(reg, "true", check_id="lint")
    assert not finish(reg)["completion_allowed"]
    verify(reg, "true", scope="new description", check_id="unit")
    assert finish(reg)["status"] == "SUCCEEDED"


def test_explicit_replacement_does_not_remove_required_command(target):
    reg = registry(target, ("test -f ready",))
    check = verify(reg, "test -f ready")
    verify(reg, "true", scope="replacement", supersedes=[check["sequence"]])
    assert not finish(reg)["completion_allowed"]
    (target / "ready").touch()
    verify(reg, "test -f ready")
    # The replacement true check is stale after creating ready, and must also be rerun.
    verify(reg, "true", scope="replacement")
    assert finish(reg)["status"] == "SUCCEEDED"


def test_default_time_budget_records_delay_without_expiring_across_resume():
    now = [0.0]
    config = RunBudget()
    budget = config.start(clock=lambda: now[0])
    now[0] = 100_000
    state = budget.snapshot()
    assert state["active_seconds_used"] == 100_000
    assert state["max_run_seconds"] is None
    assert math.isinf(budget.remaining_seconds())
    resumed = RunBudgetTracker.from_snapshot(config, state, clock=lambda: now[0])
    resumed.consume_step()
    assert resumed.snapshot()["active_seconds_used"] == 100_000


def test_timeout_retries_request_without_replaying_completed_write(target, tmp_path):
    plan = PlanHistory.for_task("Check")
    checks = []
    artifacts = RunArtifacts(tmp_path / "state", secrets=[])

    class Model:
        model_name = "offline-timeout"
        calls = 0

        def complete(self, messages, tools):
            self.calls += 1
            if self.calls == 1:
                return AssistantTurn(
                    tool_calls=[ToolCall("write", "run_command", {"command": "echo once >> file.txt"})]
                )
            if self.calls == 2:
                raise TimeoutError("temporary upstream delay")
            return AssistantTurn(
                tool_calls=[
                    ToolCall(
                        "verify",
                        "verify_task",
                        {"command": 'test "$(wc -l < file.txt)" -eq 2', "scope": "written once", "reason": "check"},
                    ),
                    ToolCall("finish", "finish_task", {"root_cause": "checked", "changes": ["checked"]}),
                ]
            )

    delays = []
    result = AgentRuntime(
        Model(),
        create_tool_registry(LocalExecutionEnvironment(target), target, plan, verifications=checks),
        artifacts,
        plan,
        sleeper=delays.append,
        verifications=checks,
    ).run("Check", target)
    assert result.status == "SUCCEEDED"
    assert (target / "file.txt").read_text() == "old\nonce\n"
    assert delays == [0.25]
    trace = artifacts.read_trace()
    assert sum(e["type"] == "model_request" for e in trace) == 3
    assert sum(e["type"] == "recovery" and e["action"] == "RETRY_MODEL" for e in trace) == 1
    assert artifacts.read_checkpoint()["budget"]["requests_used"] == 3


def test_budget_exhaustion_exit_and_explicit_resume_preserve_consumption(target, tmp_path):
    class Model:
        model_name = "offline-budget"
        calls = 0

        def complete(self, messages, tools):
            self.calls += 1
            if self.calls == 1:
                return AssistantTurn(
                    tool_calls=[ToolCall("write", "run_command", {"command": "echo once >> file.txt"})]
                )
            return AssistantTurn(
                tool_calls=[
                    ToolCall("verify", "verify_task", {"command": "true", "scope": "check", "reason": "check"}),
                    ToolCall("finish", "finish_task", {"root_cause": "checked", "changes": ["checked"]}),
                ]
            )

    model = Model()
    runner = CliRunner()
    app = create_app(lambda _: model)
    state = tmp_path / "state"
    first = runner.invoke(app, ["run", str(target), "--task", "Check", "--state-dir", str(state), "--max-steps", "1"])
    assert first.exit_code == 1, first.output
    directory = next(state.iterdir())
    before = json.loads((directory / "checkpoint.json").read_text())
    assert before["status"] == "BUDGET_EXCEEDED"
    refused = runner.invoke(app, ["resume", directory.name, "--state-dir", str(state)])
    assert refused.exit_code == 1
    assert "explicitly increase" in refused.output
    assert model.calls == 1
    resumed = runner.invoke(app, ["resume", directory.name, "--state-dir", str(state), "--max-steps", "3"])
    assert resumed.exit_code == 0, resumed.output
    after = json.loads((directory / "checkpoint.json").read_text())
    assert after["run_id"] == before["run_id"]
    assert after["budget"]["steps_used"] == 2
    assert after["budget"]["requests_used"] == 2
    assert after["budget"]["active_seconds_used"] >= before["budget"]["active_seconds_used"]
    assert (target / "file.txt").read_text() == "old\nonce\n"
    events = list(map(json.loads, (directory / "trace.jsonl").read_text().splitlines()))
    assert next(e for e in events if e["type"] == "budget_limits_changed")["changes"]["max_steps"] == {
        "previous": 1,
        "current": 3,
    }


def test_runtime_patch_survives_benchmark_copy_and_normalization(target, tmp_path):
    plan = PlanHistory.for_task("Check")
    artifacts = RunArtifacts(tmp_path / "state", secrets=[])

    class Model:
        model_name = "offline-patch"

        def complete(self, messages, tools):
            return AssistantTurn(
                tool_calls=[
                    ToolCall("write", "run_command", {"command": "echo new > new.txt"}),
                    ToolCall("finish", "finish_task", {"root_cause": "changed", "changes": ["new file"]}),
                ]
            )

    AgentRuntime(Model(), create_tool_registry(LocalExecutionEnvironment(target), target, plan), artifacts, plan).run(
        "Check", target
    )
    destination = tmp_path / "benchmark"
    destination.mkdir()
    _copy_runtime_artifacts(artifacts.path, destination)
    head = artifacts.read_metadata()["repository"]["head"]
    (destination / "patch.diff").write_text(capture_patch(target, head))
    raw = (destination / "runtime-patch.diff").read_bytes()
    manifest = json.loads((destination / "runtime-patch-manifest.json").read_text())
    assert hashlib.sha256(raw).hexdigest() == manifest["sha256"]
    assert raw == (artifacts.path / "patch.diff").read_bytes()
    assert manifest["bytes"] == len(raw)


@pytest.mark.parametrize(("options", "expected"), [(["--max-run-seconds", "60"], 60.0), (["--no-time-limit"], None)])
def test_resume_legacy_time_budget_can_extend_or_remove_limit(target, tmp_path, options, expected):
    class Model:
        model_name = "offline-time-resume"

        def complete(self, messages, tools):
            return AssistantTurn(
                tool_calls=[
                    ToolCall("verify", "verify_task", {"command": "true", "scope": "check", "reason": "check"}),
                    ToolCall("finish", "finish_task", {"root_cause": "checked", "changes": ["checked"]}),
                ]
            )

    # A persisted, exhausted legacy budget; source identity and all counters are real.
    state = tmp_path / "state"
    plan = PlanHistory.for_task("Check")
    artifacts = RunArtifacts(state, secrets=[])
    AgentRuntime(Model(), create_tool_registry(LocalExecutionEnvironment(target), target, plan), artifacts, plan).run(
        "Check", target
    )
    checkpoint = artifacts.read_checkpoint()
    checkpoint["environment"] = {"backend": "local"}
    checkpoint["approval_context"]["environment"] = "local"
    checkpoint["schema_version"] = 1
    checkpoint["status"] = "BUDGET_EXCEEDED"
    checkpoint["budget"]["max_run_seconds"] = 1.0
    checkpoint["budget"]["active_seconds_used"] = 2.0
    artifacts.write_checkpoint(checkpoint)
    result = CliRunner().invoke(
        create_app(lambda _: Model()), ["resume", artifacts.run_id, "--state-dir", str(state), *options]
    )
    assert result.exit_code == 0, result.output
    after = artifacts.read_checkpoint()
    assert after["budget"]["max_run_seconds"] == expected
    assert after["budget"]["active_seconds_used"] >= 2.0
    assert after["budget"]["steps_used"] > checkpoint["budget"]["steps_used"]


def test_legacy_verification_can_be_replaced_after_scope_rename(target):
    reg = registry(target)
    check = verify(reg, "test -f ready", "old description")
    for key in ("check_id", "explicit_check_id", "supersedes"):
        check.pop(key)
    (target / "ready").touch()
    verify(reg, "test -f ready", "new description")
    assert finish(reg)["status"] == "SUCCEEDED"
