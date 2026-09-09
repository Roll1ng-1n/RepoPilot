"""Regressions derived from the real-model protocol and recovery failures."""

from __future__ import annotations

import json

import pytest

from repopilot.approval import ApprovalContext, ApprovalPolicy, RiskDecision
from repopilot.artifacts import RunArtifacts
from repopilot.budget import RunBudget
from repopilot.context import ContextManager
from repopilot.environment import LocalExecutionEnvironment
from repopilot.model import AssistantTurn, LiteLLMToolCallingModel, ToolCall
from repopilot.plan import PlanHistory
from repopilot.requests import RequestExecutor
from repopilot.runtime import AgentRuntime
from repopilot.tools import create_tool_registry
from tests.repopilot.test_issue_regressions import target  # noqa: F401


def test_stream_preserves_arrival_order_for_interleaved_calls_and_usage(monkeypatch, tmp_path):
    import litellm
    from litellm.types.utils import ModelResponseStream

    fragments = [
        [{"index": 0, "id": "a", "type": "function", "function": {"name": "run_command", "arguments": '{"command":'}}],
        [{"index": 1, "id": "b", "type": "function", "function": {"name": "read_file", "arguments": '{"path":'}}],
        [
            {"index": 0, "function": {"arguments": '"echo hello"}'}},
            {"index": 1, "function": {"arguments": '"file.txt"}'}},
        ],
    ]
    chunks = []
    for index, calls in enumerate(fragments):
        chunk = ModelResponseStream(
            id="response", model="openai/test", choices=[{"index": 0, "delta": {"tool_calls": calls}}]
        )
        chunk._hidden_params["created_at"] = 10 - index
        chunks.append(chunk)
    chunks.append(
        ModelResponseStream(
            id="response",
            model="openai/test",
            choices=[{"index": 0, "delta": {}, "finish_reason": "tool_calls"}],
            usage={"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
        )
    )
    chunks[-1]._hidden_params["created_at"] = 1
    monkeypatch.setattr(litellm, "completion", lambda **kwargs: iter(chunks))
    model = LiteLLMToolCallingModel(model_name="openai/test", model_kwargs={"stream": True})
    artifacts = RunArtifacts(tmp_path / "runs", secrets=[])
    turn = RequestExecutor(model, RunBudget().start(), artifacts).complete([], [])
    assert [(c.id, c.name, c.arguments) for c in turn.tool_calls] == [
        ("a", "run_command", {"command": "echo hello"}),
        ("b", "read_file", {"path": "file.txt"}),
    ]
    assert turn.usage["total_tokens"] == 5
    assert [c._hidden_params["created_at"] for c in chunks] == [10, 9, 8, 1]
    event = [e for e in artifacts.read_trace() if e["type"] == "model_response"][0]
    captured = [json.loads(line) for line in (artifacts.path / event["stream_artifact"]).read_text().splitlines()]
    assert [e["sequence"] for e in captured] == [0, 1, 2, 3]
    assert captured[0]["chunk"]["choices"][0]["delta"]["tool_calls"][0]["function"]["arguments"] == '{"command":'


def test_invalid_raw_arguments_are_preserved_and_redacted(monkeypatch, tmp_path):
    import litellm

    monkeypatch.setattr(
        litellm,
        "completion",
        lambda **kwargs: {
            "choices": [
                {
                    "finish_reason": "tool_calls",
                    "message": {
                        "tool_calls": [
                            {"id": "bad", "function": {"name": "run_command", "arguments": "broken secret-fixture"}}
                        ]
                    },
                }
            ]
        },
    )
    artifacts = RunArtifacts(tmp_path / "runs", secrets=["secret-fixture"])
    turn = RequestExecutor(LiteLLMToolCallingModel(model_name="openai/test"), RunBudget().start(), artifacts).complete(
        [], []
    )
    assert turn.tool_calls[0].protocol_error
    event = artifacts.read_trace()[-1]
    assert "secret-fixture" not in json.dumps(event)
    assert event["tool_calls"][0]["raw_arguments"].startswith("broken ")


def test_block_patch_applies_multiple_files_atomically_and_keeps_delete_risk(target):
    plan = PlanHistory.for_task("repair")
    registry = create_tool_registry(LocalExecutionEnvironment(target), target, plan)
    (target / "delete.txt").write_text("remove\n")
    patch = "*** Begin Patch\n*** Update File: file.txt\n@@\n-old\n+new\n*** Add File: nested/added.txt\n+created\n*** Delete File: delete.txt\n*** End Patch"
    prepared = registry.prepare(ToolCall("patch", "apply_patch", {"patch": patch}))
    assert not isinstance(prepared, dict)
    assert (target / "file.txt").read_text() == "old\n"
    policy = ApprovalPolicy(ApprovalContext(environment="local"))
    assert policy.assess(prepared.snapshot).decision is RiskDecision.REQUIRE_APPROVAL
    observation = registry.execute(prepared)
    assert observation["ok"] and observation["result"]["applied"]
    assert (target / "file.txt").read_text() == "new\n"
    assert (target / "nested/added.txt").read_text() == "created\n"
    assert not (target / "delete.txt").exists()


def test_invalid_later_block_does_not_partially_apply_earlier_file(target):
    registry = create_tool_registry(LocalExecutionEnvironment(target), target, PlanHistory.for_task("repair"))
    (target / "ambiguous.txt").write_text("same\nsame\n")
    patch = "*** Begin Patch\n*** Update File: file.txt\n@@\n-old\n+new\n*** Update File: ambiguous.txt\n@@\n-same\n+other\n*** End Patch"
    observation = registry.dispatch(ToolCall("patch", "apply_patch", {"patch": patch}))
    assert observation["error"] == "invalid_patch"
    assert "ambiguous" in observation["details"]
    assert (target / "file.txt").read_text() == "old\n"


def test_block_patch_discovers_scoped_instructions_before_mutation(target):
    (target / "nested").mkdir()
    (target / "nested/AGENTS.md").write_text("Retain the public API.")
    (target / "nested/code.py").write_text("old\n")
    registry = create_tool_registry(LocalExecutionEnvironment(target), target, PlanHistory.for_task("repair"))
    context = ContextManager()
    registry.instruction_observer = context.observe_repository_instruction
    call = ToolCall(
        "patch",
        "apply_patch",
        {"patch": "*** Begin Patch\n*** Update File: nested/code.py\n@@\n-old\n+new\n*** End Patch"},
    )
    assert registry.dispatch(call)["error"] == "repository_instructions_discovered"
    assert (target / "nested/code.py").read_text() == "old\n"
    assert registry.dispatch(call)["result"]["applied"]


@pytest.mark.parametrize("contents", ["old", "old\r\n"])
def test_block_patch_handles_missing_final_newline_and_crlf(target, contents):
    (target / "file.txt").write_bytes(contents.encode())
    registry = create_tool_registry(LocalExecutionEnvironment(target), target, PlanHistory.for_task("repair"))
    result = registry.dispatch(
        ToolCall(
            "patch",
            "apply_patch",
            {"patch": "*** Begin Patch\n*** Update File: file.txt\n@@\n-old\n+new\n*** End Patch"},
        )
    )
    assert result["result"]["applied"], result
    assert (target / "file.txt").read_bytes() == (b"new\r\n" if "\r\n" in contents else b"new\n")


class ScriptedModel:
    model_name = "regression"

    def __init__(self, calls):
        self.calls = iter(calls)

    def complete(self, messages, tools):
        return AssistantTurn(tool_calls=[next(self.calls)])


def test_recovery_requests_one_valid_model_replan_without_double_charge(target, tmp_path):
    plan = PlanHistory.for_task("repair")
    model = ScriptedModel(
        [
            ToolCall("bad1", "unknown", {}),
            ToolCall("bad2", "unknown", {}),
            ToolCall(
                "invalid",
                "replan",
                {
                    "reason": "new",
                    "steps": [
                        {"id": "dup", "description": "one", "completion_condition": "checked"},
                        {"id": "dup", "description": "two", "completion_condition": "checked"},
                    ],
                },
            ),
            ToolCall(
                "valid",
                "replan",
                {"reason": "new", "steps": [{"id": "fix", "description": "repair", "completion_condition": "checked"}]},
            ),
            ToolCall("verify", "verify_task", {"command": "true", "scope": "task", "reason": "checked"}),
            ToolCall("finish", "finish_task", {"root_cause": "done", "changes": ["done"]}),
        ]
    )
    artifacts = RunArtifacts(tmp_path / "runs", secrets=[])
    result = AgentRuntime(
        model,
        create_tool_registry(LocalExecutionEnvironment(target), target, plan),
        artifacts,
        plan,
        RunBudget(max_replans=1, max_consecutive_failures=2),
    ).run("repair", target)
    assert result.status == "SUCCEEDED"
    assert artifacts.read_metadata()["budget"]["replans_used"] == 1
    assert plan.current.version == 2
    assert sum(e["type"] == "replan_requested" for e in artifacts.read_trace()) == 1
    assert sum(e["type"] == "plan_replanned" for e in artifacts.read_trace()) == 1


def test_no_planning_run_can_patch_verify_and_finish_without_hidden_step_ids(target, tmp_path):
    plan = PlanHistory.for_task("repair")
    registry = create_tool_registry(LocalExecutionEnvironment(target), target, plan, planning_enabled=False)
    schemas = {s["function"]["name"]: s["function"]["parameters"] for s in registry.schemas}
    assert "replan" not in schemas and "update_plan" not in schemas
    assert "step_ids" not in schemas["verify_task"]["properties"]
    model = ScriptedModel(
        [
            ToolCall(
                "patch",
                "apply_patch",
                {"patch": "*** Begin Patch\n*** Update File: file.txt\n@@\n-old\n+new\n*** End Patch"},
            ),
            ToolCall(
                "verify",
                "verify_task",
                {"command": 'test "$(cat file.txt)" = new', "scope": "task", "reason": "check fix"},
            ),
            ToolCall("finish", "finish_task", {"root_cause": "old content", "changes": ["updated file"]}),
        ]
    )
    artifacts = RunArtifacts(tmp_path / "runs", secrets=[])
    result = AgentRuntime(model, registry, artifacts, plan).run("repair", target)
    assert result.status == "SUCCEEDED"
    assert artifacts.read_metadata()["completion_decision"]["covered_plan_steps"] == ["complete-task"]
