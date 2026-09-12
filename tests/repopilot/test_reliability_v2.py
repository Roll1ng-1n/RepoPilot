"""Fault injection and artifact replay acceptance tests for issues #19–#24."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time

import pytest

from repopilot.artifacts import RunArtifacts
from repopilot.budget import BudgetExceeded, RunBudget, RunBudgetTracker
from repopilot.context import ContextManager
from repopilot.environment import Command, DockerExecutionEnvironment, LocalExecutionEnvironment
from repopilot.locking import run_lock
from repopilot.model import AssistantTurn, ToolCall
from repopilot.plan import PlanHistory
from repopilot.profile import applicable_instructions
from repopilot.repository_snapshot import diff, snapshot
from repopilot.requests import RequestExecutor
from repopilot.runtime import AgentRuntime
from repopilot.tools import create_tool_registry
from tests.repopilot.test_issue_regressions import target  # noqa: F401

DRIVER = """
import os, sys
from pathlib import Path
from repopilot.artifacts import RunArtifacts
from repopilot.environment import LocalExecutionEnvironment
from repopilot.model import AssistantTurn, ToolCall
from repopilot.plan import PlanHistory
from repopilot.runtime import AgentRuntime
from repopilot.tools import create_tool_registry
root, state = map(Path, sys.argv[1:])
class Environment(LocalExecutionEnvironment):
    def execute(self, command):
        result = super().execute(command)
        if command.argv == ("bash", "-lc", "echo once >> file.txt"):
            os._exit(91)
        return result
class Model:
    model_name = "fault-injection"
    def complete(self, messages, tools):
        return AssistantTurn(tool_calls=[ToolCall("write", "run_command", {"command": "echo once >> file.txt"}), ToolCall("read", "read_file", {"path": "file.txt"})])
plan = PlanHistory.for_task("Fix")
artifacts = RunArtifacts(state, secrets=[])
AgentRuntime(Model(), create_tool_registry(Environment(root), root, plan), artifacts, plan).run("Fix", root)
"""


def test_real_process_crash_recovers_unknown_write_and_remaining_calls(target, tmp_path):
    state = tmp_path / "runs"
    crashed = subprocess.run([sys.executable, "-c", DRIVER, str(target), str(state)], capture_output=True, timeout=10)
    assert crashed.returncode == 91, crashed.stderr
    run = next(state.iterdir())
    artifacts = RunArtifacts.reopen(state, run.name, secrets=[])
    checkpoint = artifacts.read_checkpoint()
    assert checkpoint["status"] == "RUNNING"
    assert checkpoint["in_flight_tool_call"] == "write"

    class Model:
        model_name = "resumed"

        def complete(self, messages, tools):
            observations = [m for m in messages if m.get("role") == "tool"]
            assert [m["tool_call_id"] for m in observations] == ["write", "read"]
            assert "interrupted_result_unknown" in observations[0]["content"]
            return AssistantTurn(
                tool_calls=[ToolCall("finish", "finish_task", {"root_cause": "done", "changes": ["done"]})]
            )

    plan = PlanHistory.from_dict(checkpoint["plan_history"])
    runtime = AgentRuntime(
        Model(), create_tool_registry(LocalExecutionEnvironment(target), target, plan), artifacts, plan
    )
    result = runtime.resume(checkpoint, target)
    assert result.status == "UNVERIFIED"
    assert (target / "file.txt").read_text().count("once") == 1


def test_concurrent_process_cannot_acquire_same_run_lock(tmp_path):
    code = "from repopilot.locking import run_lock; from pathlib import Path; import sys\nwith run_lock(Path(sys.argv[1])):\n print('ready', flush=True)\n sys.stdin.read()"
    process = subprocess.Popen(
        [sys.executable, "-c", code, str(tmp_path)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True
    )
    try:
        assert process.stdout.readline().strip() == "ready"
        with pytest.raises(ValueError, match="active"):
            with run_lock(tmp_path):
                pytest.fail("second executor entered")
    finally:
        process.communicate("done", timeout=5)
    with run_lock(tmp_path):
        pass


def test_model_request_is_cancelled_before_its_delayed_side_effect(tmp_path):
    class Model:
        model_name = "slow"

        def complete(self, messages, tools):
            time.sleep(1)
            (tmp_path / "late").write_text("must not happen")

    budget = RunBudget(max_run_seconds=0.05).start()
    executor = RequestExecutor(Model(), budget, RunArtifacts(tmp_path / "runs", secrets=[]))
    started = time.monotonic()
    with pytest.raises(BudgetExceeded, match="run_time"):
        executor.complete([], [])
    assert time.monotonic() - started < 0.5
    assert not (tmp_path / "late").exists()
    assert budget.requests_used == 1


def test_summary_main_and_resume_share_token_and_cost_accounting(tmp_path):
    class Model:
        model_name = "metered"

        def complete(self, messages, tools):
            return AssistantTurn(content="{}", usage={"total_tokens": 5}, cost=0.25)

    config = RunBudget(max_tokens=10, max_cost_usd=1)
    budget = config.start()
    artifacts = RunArtifacts(tmp_path / "runs", secrets=[])
    executor = RequestExecutor(Model(), budget, artifacts)
    executor.complete([], [])
    executor.for_summary().complete([], [])
    restored = RunBudgetTracker.from_snapshot(config, budget.snapshot())
    assert restored.tokens_used == 10
    assert restored.cost_used == 0.5
    with pytest.raises(BudgetExceeded, match="tokens"):
        RequestExecutor(Model(), restored, artifacts).complete([], [])
    assert [e["purpose"] for e in artifacts.read_trace() if e["type"] == "model_response"] == ["main", "summary"]


@pytest.mark.parametrize(
    ("config", "reason"),
    [(RunBudget(max_tokens=10), "unknown_token_usage"), (RunBudget(max_cost_usd=1), "unknown_cost")],
)
def test_unknown_usage_stops_subsequent_requests(tmp_path, config, reason):
    class Model:
        model_name = "unknown"

        def complete(self, messages, tools):
            return AssistantTurn()

    executor = RequestExecutor(Model(), config.start(), RunArtifacts(tmp_path / "runs", secrets=[]))
    executor.complete([], [])
    with pytest.raises(BudgetExceeded, match=reason):
        executor.complete([], [])


def test_snapshot_replays_dirty_baseline_commits_binary_and_rename(target, tmp_path):
    def git(*args):
        return subprocess.run(["git", "-C", str(target), *args], check=True, capture_output=True).stdout

    (target / "file.txt").write_text("user change\n")
    (target / "user.txt").write_text("user untracked\n")
    before_index = git("diff", "--cached", "--binary")
    initial = snapshot(target)
    assert git("diff", "--cached", "--binary") == before_index
    (target / "file.txt").rename(target / "renamed.txt")
    (target / "binary.dat").write_bytes(bytes(range(256)) * 400)
    git("add", "--all")
    git("-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-qm", "agent commit")
    (target / "renamed.txt").write_text("agent result\n")
    final = snapshot(target)
    baseline_patch = diff(target, initial["state"]["head"], initial["tree"])
    patch = diff(target, initial["tree"], final["tree"])
    assert "user.txt" not in patch
    replay = tmp_path / "replay"
    subprocess.run(["git", "clone", "--quiet", str(target), str(replay)], check=True)
    subprocess.run(["git", "-C", str(replay), "checkout", "--quiet", initial["state"]["head"]], check=True)
    for payload in (baseline_patch, patch):
        subprocess.run(["git", "-C", str(replay), "apply", "--binary", "-"], input=payload, text=True, check=True)
    assert (replay / "binary.dat").read_bytes() == (target / "binary.dat").read_bytes()
    assert (replay / "renamed.txt").read_text() == "agent result\n"
    assert (replay / "user.txt").read_text() == "user untracked\n"
    assert not (replay / "file.txt").exists()


def test_scoped_instructions_exclude_sibling_and_require_review_before_patch(target, tmp_path):
    (target / "AGENTS.md").write_text("Root instructions")
    (target / "nested").mkdir()
    (target / "nested" / "AGENTS.md").write_text("Nested instructions")
    (target / "sibling").mkdir()
    (target / "sibling" / "AGENTS.md").write_text("Sibling instructions")
    instructions = applicable_instructions(target, "nested/new.py")
    assert [i["source"] for i in instructions] == ["AGENTS.md", "nested/AGENTS.md"]
    context = ContextManager()
    reg = create_tool_registry(LocalExecutionEnvironment(target), target, PlanHistory.for_task("Fix"))
    reg.instruction_observer = context.observe_repository_instruction
    call = ToolCall("patch", "apply_patch", {"patch": "--- /dev/null\n+++ b/nested/new.py\n@@ -0,0 +1 @@\n+pass\n"})
    observation = reg.dispatch(call)
    assert observation["error"] == "repository_instructions_discovered"
    assert not (target / "nested" / "new.py").exists()
    assert reg.dispatch(call)["result"]["applied"]


def test_complete_tool_artifact_can_be_read_after_preview(target, tmp_path):
    reg = create_tool_registry(LocalExecutionEnvironment(target), target, PlanHistory.for_task("Fix"))
    reg.artifacts = RunArtifacts(tmp_path / "runs", secrets=[])
    original = {"ok": True, "result": {"stdout": "x" * 30000 + "END"}}
    preview = reg.model_observation(original)
    assert preview["truncated"]
    artifact = preview["artifact"]
    chunks = []
    offset = 0
    while offset is not None:
        result = reg.dispatch(ToolCall("read", "read_artifact", {"artifact": artifact, "offset": offset}))["result"]
        chunks.append(result["content"])
        offset = result["next_offset"]
    assert json.loads("".join(chunks)) == original


def test_context_bound_keeps_tool_pairs_and_rejects_oversized_constraints():
    context = ContextManager()
    context.context_window_tokens = 8000
    context.output_reserve_tokens = 1000
    messages = [{"role": "system", "content": "policy"}, {"role": "user", "content": "task"}]
    for i in range(20):
        messages += [
            {"role": "assistant", "tool_calls": [{"id": str(i), "function": {"name": "read_file", "arguments": "{}"}}]},
            {"role": "tool", "tool_call_id": str(i), "content": "x" * 2000},
        ]
    bounded = context.bound_request(messages, [])
    calls = [c["id"] for m in bounded for c in m.get("tool_calls", [])]
    results = [m["tool_call_id"] for m in bounded if m["role"] == "tool"]
    assert calls == results
    assert len(json.dumps(bounded).encode()) < 6000
    with pytest.raises(BudgetExceeded, match="context_window"):
        context.bound_request([{"role": "system", "content": "x" * 20000}], [])


def test_docker_timeout_kills_container_descendants(target):
    # WSL may expose a docker shim even when Desktop integration is unavailable.
    try:
        version = subprocess.run(["docker", "version"], capture_output=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        pytest.skip("Docker is unavailable")
    if version.returncode != 0:
        pytest.skip("Docker is unavailable")
    environment = DockerExecutionEnvironment(
        target, image=os.environ.get("REPOPILOT_DOCKER_TEST_IMAGE", "python:3.12-bookworm")
    )
    try:
        result = environment.execute(
            Command(("sh", "-c", "(sleep 0.3; echo leaked > late.txt) & wait"), timeout_seconds=0.05)
        )
        assert result.exit_code == -1
        time.sleep(0.4)
        assert not (target / "late.txt").exists()
    finally:
        environment.close()


def test_approved_write_crash_uses_same_inflight_recovery(target, tmp_path):
    from repopilot.approval import ApprovalContext
    from repopilot.model import ToolCall

    artifacts = RunArtifacts(tmp_path / "runs", secrets=[])
    plan = PlanHistory.for_task("Commit")

    class Model:
        model_name = "approval"

        def complete(self, messages, tools):
            return AssistantTurn(
                tool_calls=[
                    ToolCall(
                        "commit", "git_commit", {"message": "record", "reason": "requested", "paths": ["file.txt"]}
                    )
                ]
            )

    first = AgentRuntime(
        Model(),
        create_tool_registry(LocalExecutionEnvironment(target), target, plan),
        artifacts,
        plan,
        approval_context=ApprovalContext(environment="local"),
    )
    assert first.run("Commit", target).status == "WAITING_FOR_APPROVAL"
    checkpoint = artifacts.read_checkpoint()

    class InterruptedEnvironment(LocalExecutionEnvironment):
        def execute(self, command):
            if command.argv[:2] == ("git", "add"):
                super().execute(command)
                raise KeyboardInterrupt()
            return super().execute(command)

    runtime = AgentRuntime(
        Model(),
        create_tool_registry(InterruptedEnvironment(target), target, plan),
        artifacts,
        plan,
        approval_context=ApprovalContext(environment="local"),
    )
    assert runtime.resume(checkpoint, target, approval_granted=True).status == "STOPPED"
    stopped = artifacts.read_checkpoint()
    assert stopped["in_flight_tool_call"] == "commit"
    assert stopped["execution_log"]["commit"]["state"] == "in_flight"
    assert stopped["approval_request"] is None


def test_plan_revision_requires_new_step_evidence(target):
    from repopilot.plan import PlanStep

    plan = PlanHistory.for_task("Fix")
    reg = create_tool_registry(LocalExecutionEnvironment(target), target, plan)
    reg.dispatch(ToolCall("verify", "verify_task", {"command": "true", "scope": "all", "reason": "check"}))
    plan.replan([PlanStep("new-step", "New work", "Must check new requirement")], "new requirement")
    done = reg.dispatch(ToolCall("finish", "finish_task", {"root_cause": "fixed", "changes": ["fixed"]}))
    assert done["result"]["completion_allowed"] is False
    assert any(p.get("step_id") == "new-step" for p in reg.completion_decision["problems"])
    reg.dispatch(ToolCall("verify2", "verify_task", {"command": "true", "scope": "all", "reason": "new check"}))
    assert (
        reg.dispatch(ToolCall("finish2", "finish_task", {"root_cause": "fixed", "changes": ["fixed"]}))["result"][
            "status"
        ]
        == "SUCCEEDED"
    )


def test_authentication_error_stops_even_after_previous_retry_failures():
    from repopilot.recovery import Failure, FailureCategory, RecoveryAction, RecoveryController

    recovery = RecoveryController(2)
    recovery.recover(Failure(FailureCategory.MODEL_ERROR, "network"), transient_model_error=True)
    decision = recovery.recover(Failure(FailureCategory.MODEL_ERROR, "authentication"))
    assert decision.action is RecoveryAction.STOP


def test_cli_run_resume_calls_streaming_only_adapter(target, tmp_path, monkeypatch):
    from types import SimpleNamespace

    from typer.testing import CliRunner

    from repopilot.cli import create_app
    from repopilot.model import LiteLLMToolCallingModel

    calls = []

    def completion(**kwargs):
        assert kwargs["stream"] is True
        assert kwargs["timeout"] <= 10
        calls.append(kwargs)
        if len(calls) == 2:
            raise KeyboardInterrupt()
        function = (
            ("verify_task", {"command": "true", "scope": "all", "reason": "test"})
            if len(calls) == 1
            else ("finish_task", {"root_cause": "checked", "changes": ["checked"]})
        )
        response = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content=None,
                        tool_calls=[
                            SimpleNamespace(
                                id=f"call-{len(calls)}",
                                function=SimpleNamespace(name=function[0], arguments=json.dumps(function[1])),
                            )
                        ],
                    ),
                    finish_reason="tool_calls",
                )
            ],
            usage={"total_tokens": 10},
        )
        return iter([response])

    monkeypatch.setitem(
        sys.modules, "litellm", SimpleNamespace(completion=completion, stream_chunk_builder=lambda chunks: chunks[-1])
    )

    def factory(options):
        return LiteLLMToolCallingModel(
            model_name=options.model_name, api_key=options.api_key, model_kwargs=options.model_kwargs
        )

    app = create_app(factory)
    runner = CliRunner()
    state = tmp_path / "runs"
    result = runner.invoke(
        app,
        [
            "run",
            str(target),
            "--task",
            "Check",
            "--model",
            "openai/stream-only",
            "--stream",
            "--request-timeout",
            "10",
            "--state-dir",
            str(state),
        ],
    )
    assert result.exit_code == 5, result.output
    assert "STOPPED" in result.output
    run = next(state.iterdir())
    resumed = runner.invoke(app, ["resume", run.name, "--state-dir", str(state)])
    assert resumed.exit_code == 0, resumed.output
    assert "SUCCEEDED" in resumed.output
    checkpoint = json.loads((run / "checkpoint.json").read_text())
    assert checkpoint["budget"]["requests_used"] == 3
    assert len(calls) == 3


def test_context_summary_has_main_request_trace_and_usage(target, tmp_path):
    from repopilot.context import ContextStrategy, model_summary_generator

    class Model:
        model_name = "summary-metered"
        count = 0

        def complete(self, messages, tools):
            if not tools:
                return AssistantTurn(
                    content=json.dumps(
                        {"important_facts": [], "completed_work": [], "decisions": [], "open_questions": []}
                    ),
                    usage={"total_tokens": 3},
                    cost=0.1,
                )
            self.count += 1
            if self.count <= 2:
                return AssistantTurn(
                    tool_calls=[ToolCall(f"read-{self.count}", "read_file", {"path": "file.txt"})],
                    usage={"total_tokens": 5},
                    cost=0.2,
                )
            return AssistantTurn(
                tool_calls=[ToolCall("finish", "finish_task", {"root_cause": "done", "changes": ["done"]})],
                usage={"total_tokens": 5},
                cost=0.2,
            )

    model = Model()
    plan = PlanHistory.for_task("Fix")
    artifacts = RunArtifacts(tmp_path / "runs", secrets=[])
    runtime = AgentRuntime(
        model,
        create_tool_registry(LocalExecutionEnvironment(target), target, plan),
        artifacts,
        plan,
        context=ContextManager(ContextStrategy.SUMMARY, max_characters=1, summarizer=model_summary_generator(model)),
    )
    runtime.run("Fix", target)
    events = [e for e in artifacts.read_trace() if e["type"] == "model_response"]
    assert any(e["purpose"] == "summary" for e in events)
    checkpoint = artifacts.read_checkpoint()
    assert checkpoint["budget"]["tokens_used"] == sum(e["usage"]["total_tokens"] for e in events)
    assert checkpoint["budget"]["requests_used"] == len(events)
