"""Deterministic regressions for GitHub issues #19 through #24 (no paid model)."""

from __future__ import annotations

import json
import subprocess
import sys
from types import SimpleNamespace

import pytest

from repopilot.approval import ApprovalContext, ApprovalPolicy, RiskDecision, ToolCallSnapshot
from repopilot.artifacts import RunArtifacts
from repopilot.budget import BudgetExceeded, RunBudget, RunBudgetTracker
from repopilot.environment import LocalExecutionEnvironment
from repopilot.model import AssistantTurn, ModelProtocolError, ToolCall, stream_or_plain_completion
from repopilot.plan import PlanHistory
from repopilot.recovery import FailureCategory, classify_tool_failure
from repopilot.runtime import AgentRuntime
from repopilot.tools import create_tool_registry


@pytest.fixture
def target(tmp_path):
    target = tmp_path / "target"
    target.mkdir()
    subprocess.run(["git", "init", "-q", str(target)], check=True)
    (target / "file.txt").write_text("old\n")
    subprocess.run(["git", "-C", str(target), "add", "."], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(target),
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-qm",
            "initial",
        ],
        check=True,
    )
    return target


def registry(target, required=()):
    return create_tool_registry(
        LocalExecutionEnvironment(target), target, PlanHistory.for_task("Fix"), required_verifications=required
    )


def verify(reg, command="true", scope="test"):
    return reg.dispatch(ToolCall("verify", "verify_task", {"command": command, "scope": scope, "reason": "check"}))


def finish(reg):
    return reg.dispatch(ToolCall("finish", "finish_task", {"root_cause": "fixed", "changes": ["fixed"]}))["result"]


def test_latest_failed_check_prevents_completion_and_can_recover(target):
    reg = registry(target)
    verify(reg)
    verify(reg, "false")
    assert finish(reg)["completion_allowed"] is False
    verify(reg)
    assert finish(reg)["status"] == "SUCCEEDED"


def test_modified_repository_invalidates_previous_evidence(target):
    reg = registry(target)
    verify(reg)
    (target / "file.txt").write_text("changed\n")
    assert finish(reg)["completion_allowed"] is False
    verify(reg)
    assert finish(reg)["status"] == "SUCCEEDED"


def test_mutating_verification_does_not_prove_its_output(target):
    reg = registry(target)
    verify(reg, "echo changed > file.txt")
    assert finish(reg)["completion_allowed"] is False


def test_required_checks_are_independent(target):
    reg = registry(target, ("true", "test -f file.txt"))
    verify(reg)
    assert finish(reg)["completion_allowed"] is False
    verify(reg, "test -f file.txt", "file")
    assert finish(reg)["status"] == "SUCCEEDED"


def test_patch_failure_enters_recovery_but_search_miss_does_not(target):
    reg = registry(target)
    result = reg.dispatch(ToolCall("bad", "apply_patch", {"patch": "invalid patch"}))
    assert classify_tool_failure("apply_patch", result).category is FailureCategory.TOOL_ERROR
    miss = reg.dispatch(ToolCall("miss", "search_code", {"query": "absent-text"}))
    assert classify_tool_failure("search_code", miss) is None


@pytest.mark.parametrize("suffix", ["", "\t1970-01-01"])
def test_standard_unified_deletion_requires_approval(suffix):
    call = ToolCall(
        "delete", "apply_patch", {"patch": "--- a/file.txt\n+++ /dev/null" + suffix + "\n@@ -1 +0,0 @@\n-old\n"}
    )
    decision = ApprovalPolicy(ApprovalContext(environment="local")).assess(ToolCallSnapshot.from_tool_call(call))
    assert decision.decision is RiskDecision.REQUIRE_APPROVAL


def test_staged_large_patch_is_complete(target):
    text = "".join(f"line {i:06d}\n" for i in range(4000))
    (target / "large.txt").write_text(text)
    subprocess.run(["git", "-C", str(target), "add", "large.txt"], check=True)
    patch = registry(target).capture_diff()["result"]["patch"]
    assert len(patch) > 20_000
    assert "+line 003999" in patch
    subprocess.run(["git", "-C", str(target), "apply", "--reverse", "--check", "-"], input=patch, text=True, check=True)


def test_file_pagination_ignores_venv_and_search_has_global_limit(target):
    (target / ".gitignore").write_text(".venv/\n")
    (target / ".venv").mkdir()
    (target / ".venv" / "noise").write_text("needle\n")
    for i in range(4):
        (target / f"match{i}").write_text("needle\n" * 3)
    reg = registry(target)
    first = reg.dispatch(ToolCall("list", "list_files", {"max_results": 2}))["result"]
    assert first["next_offset"] == 2
    assert ".venv" not in first["stdout"]
    result = reg.dispatch(ToolCall("search", "search_code", {"query": "needle", "max_results": 2}))["result"]
    assert len(result["stdout"].splitlines()) == 2
    assert result["truncated"]


def test_resume_carries_active_time_but_not_offline_wait():
    now = [0.0]
    config = RunBudget(max_run_seconds=10)
    tracker = config.start(clock=lambda: now[0])
    now[0] = 9
    snapshot = tracker.snapshot()
    now[0] = 1000
    resumed = RunBudgetTracker.from_snapshot(config, snapshot, clock=lambda: now[0])
    assert resumed.remaining_seconds() == 1
    now[0] += 1
    with pytest.raises(BudgetExceeded, match="run_time"):
        resumed.consume_step()


def test_empty_stream_and_failed_aggregation_are_explicit():
    fake = SimpleNamespace(completion=lambda **kw: iter([]))
    with pytest.raises(ModelProtocolError, match="empty stream"):
        stream_or_plain_completion(fake, {}, force_stream=True)
    fake.completion = lambda **kw: iter(["chunk"])
    fake.stream_chunk_builder = lambda chunks: None
    with pytest.raises(ModelProtocolError, match="aggregation"):
        stream_or_plain_completion(fake, {}, force_stream=True)


def test_interrupted_batch_preserves_remaining_calls_without_replaying_write(target, tmp_path):
    plan = PlanHistory.for_task("Fix")
    artifacts = RunArtifacts(tmp_path / "runs", secrets=[])

    class InterruptedEnvironment(LocalExecutionEnvironment):
        def execute(self, command):
            if command.argv == ("bash", "-lc", "echo once >> file.txt"):
                super().execute(command)
                raise KeyboardInterrupt()
            return super().execute(command)

    class Model:
        model_name = "scripted"

        def complete(self, messages, tools):
            return AssistantTurn(
                tool_calls=[
                    ToolCall("write", "run_command", {"command": "echo once >> file.txt"}),
                    ToolCall("list", "list_files", {}),
                ]
            )

    reg = create_tool_registry(InterruptedEnvironment(target), target, plan)
    result = AgentRuntime(Model(), reg, artifacts, plan).run("Fix", target)
    assert result.status == "STOPPED"
    checkpoint = artifacts.read_checkpoint()
    assert [c["id"] for c in checkpoint["pending_tool_calls"]] == ["write", "list"]

    class ResumeModel:
        model_name = "scripted"

        def complete(self, messages, tools):
            results = [m["tool_call_id"] for m in messages if m["role"] == "tool"]
            assert results == ["write", "list"]
            return AssistantTurn(
                tool_calls=[ToolCall("finish", "finish_task", {"root_cause": "done", "changes": ["done"]})]
            )

    AgentRuntime(
        ResumeModel(), create_tool_registry(LocalExecutionEnvironment(target), target, plan), artifacts, plan
    ).resume(checkpoint, target)
    assert (target / "file.txt").read_text().count("once") == 1


def test_startup_banner_does_not_pollute_stdout():
    result = subprocess.run(
        [sys.executable, "-c", "import minisweagent; print('123')"], capture_output=True, text=True, check=True
    )
    assert json.loads(result.stdout) == 123


def test_timeout_kills_descendant_before_later_write(target):
    import time

    from repopilot.environment import Command

    result = LocalExecutionEnvironment(target).execute(
        Command(("sh", "-c", "(sleep 0.15; echo leaked > late.txt) & wait"), timeout_seconds=0.03)
    )
    assert result.exit_code == -1
    time.sleep(0.2)
    assert not (target / "late.txt").exists()


def test_malformed_native_arguments_keep_id_and_cannot_execute(target):
    from repopilot.model import LiteLLMToolCallingModel

    call = LiteLLMToolCallingModel._to_tool_call(
        SimpleNamespace(id="original-id", function=SimpleNamespace(name="view_diff", arguments='{"broken":'))
    )
    restored = ToolCallSnapshot.from_dict(ToolCallSnapshot.from_tool_call(call).to_dict()).to_tool_call()
    assert restored.id == "original-id"
    observation = registry(target).dispatch(restored)
    assert observation["ok"] is False
    assert observation["error"] == "invalid_tool_arguments"


def test_connection_config_precedence_and_checkpoint_fallback(tmp_path, monkeypatch):
    from repopilot.cli import _connection_options

    env_file = tmp_path / "config.env"
    env_file.write_text(
        "REPOPILOT_MODEL=file/model\nREPOPILOT_API_KEY=file-secret\nREPOPILOT_STREAM=true\nREPOPILOT_MAX_OUTPUT_TOKENS=50\n"
    )
    for key in ("REPOPILOT_MODEL", "REPOPILOT_API_KEY", "REPOPILOT_STREAM", "REPOPILOT_MAX_OUTPUT_TOKENS"):
        monkeypatch.delenv(key, raising=False)
    saved = {"model_name": "saved/model", "model_kwargs": {"timeout": 10, "stream": False}}
    options = _connection_options(None, None, None, None, None, None, env_file, saved)
    assert options.model_name == "file/model"
    assert options.model_kwargs == {"timeout": 10, "stream": True, "max_tokens": 50}
    monkeypatch.setenv("REPOPILOT_MODEL", "env/model")
    monkeypatch.setenv("REPOPILOT_STREAM", "false")
    options = _connection_options(None, None, None, None, None, None, env_file, saved)
    assert options.model_name == "env/model"
    assert options.model_kwargs["stream"] is False
    options = _connection_options("cli/model", "cli-secret", None, True, 3, 20, env_file, saved)
    assert options.model_name == "cli/model"
    assert options.api_key == "cli-secret"
    assert options.model_kwargs == {"timeout": 3, "stream": True, "max_tokens": 20}


def test_cli_stream_options_survive_resume_without_persisting_key(target, tmp_path):
    from typer.testing import CliRunner

    from repopilot.cli import create_app

    seen = []

    class Model:
        model_name = "scripted/streaming-only"

        def complete(self, messages, tools):
            raise KeyboardInterrupt()

    def factory(options):
        seen.append(options)
        return Model()

    state = tmp_path / "runs"
    runner = CliRunner()
    app = create_app(factory)
    result = runner.invoke(
        app,
        [
            "run",
            str(target),
            "--task",
            "Fix",
            "--state-dir",
            str(state),
            "--stream",
            "--request-timeout",
            "2",
            "--max-output-tokens",
            "99",
            "--api-key",
            "never-persist-this-key",
            "--required-verification",
            "true",
        ],
    )
    assert result.exit_code == 5, result.output
    run = next(state.iterdir())
    assert "never-persist-this-key" not in (run / "checkpoint.json").read_text()
    resumed = runner.invoke(app, ["resume", run.name, "--state-dir", str(state)])
    assert resumed.exit_code == 5, resumed.output
    assert seen[0].model_kwargs == seen[1].model_kwargs == {"stream": True, "timeout": 2, "max_tokens": 99}
    checkpoint = json.loads((run / "checkpoint.json").read_text())
    assert checkpoint["environment"]["required_verifications"] == ["true"]
    inspected = subprocess.run(
        [
            sys.executable,
            "-c",
            "from repopilot.cli import app; app()",
            "inspect",
            run.name,
            "--state-dir",
            str(state),
            "--json",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(inspected.stdout)["status"] == "STOPPED"


def test_doctor_never_constructs_model_or_prints_key(monkeypatch):
    from typer.testing import CliRunner

    import repopilot.doctor as doctor
    from repopilot.cli import create_app

    monkeypatch.setattr(doctor.shutil, "which", lambda name: None)

    def forbidden(options):
        raise AssertionError("doctor must not construct a model")

    result = CliRunner().invoke(create_app(forbidden), ["doctor", "--api-key", "never-print-secret"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)
    assert data["paid_requests"] == 0
    assert data["checks"]["docker"]["status"] == "cli_missing"
    assert "never-print-secret" not in result.output


def test_slow_model_cannot_start_tools_after_budget_deadline(target, tmp_path):
    import time

    class SlowModel:
        model_name = "scripted/slow"

        def complete(self, messages, tools):
            time.sleep(0.08)
            return AssistantTurn(tool_calls=[ToolCall("write", "run_command", {"command": "echo late > late.txt"})])

    plan = PlanHistory.for_task("Fix")
    artifacts = RunArtifacts(tmp_path / "runs", secrets=[])
    result = AgentRuntime(
        SlowModel(),
        create_tool_registry(LocalExecutionEnvironment(target), target, plan),
        artifacts,
        plan,
        RunBudget(max_run_seconds=0.06),
    ).run("Fix", target)
    assert result.status == "BUDGET_EXCEEDED"
    assert not (target / "late.txt").exists()


def test_tool_batch_stops_at_command_deadline(target, tmp_path):
    class Model:
        model_name = "scripted/batch"

        def complete(self, messages, tools):
            return AssistantTurn(
                tool_calls=[
                    ToolCall("slow", "run_command", {"command": "sleep 1"}),
                    ToolCall("write", "run_command", {"command": "echo late > late.txt"}),
                ]
            )

    plan = PlanHistory.for_task("Fix")
    artifacts = RunArtifacts(tmp_path / "runs", secrets=[])
    result = AgentRuntime(
        Model(),
        create_tool_registry(LocalExecutionEnvironment(target), target, plan),
        artifacts,
        plan,
        RunBudget(max_run_seconds=0.1),
    ).run("Fix", target)
    assert result.status == "BUDGET_EXCEEDED"
    assert not (target / "late.txt").exists()
