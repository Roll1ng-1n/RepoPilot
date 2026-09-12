"""Replay the real #27 failure inputs without paid requests."""

import copy
import json
import shutil
import subprocess
import sys
from pathlib import Path

from repopilot.artifacts import RunArtifacts
from repopilot.budget import RunBudget
from repopilot.context import ContextManager
from repopilot.context_memory import byte_size
from repopilot.environment import LocalExecutionEnvironment
from repopilot.model import AssistantTurn, ToolCall
from repopilot.plan import PlanHistory
from repopilot.runtime import AgentRuntime
from repopilot.tools import create_tool_registry

EVIDENCE = Path(__file__).resolve().parents[2] / "docs/evidence/issue24-effective-ablation"


def receipts(messages):
    entry = next(m for m in messages if (m.get("content") or "").startswith("Historical tool receipts"))
    return json.loads(entry["content"][entry["content"].index("{") :])["historical_tool_receipts"]


def assert_protocol(messages):
    pending = set()
    for m in messages:
        if m["role"] == "assistant":
            assert not pending
            pending = {c["id"] for c in m.get("tool_calls", [])}
        elif m["role"] == "tool":
            assert m["tool_call_id"] in pending
            pending.remove(m["tool_call_id"])
    assert not pending


def test_real_checkpoint_prefixes_retain_initial_check_contracts_and_protocol(tmp_path):
    for model in ["gpt-5.6-sol", "gpt-5.6-luna"]:
        folder = EVIDENCE / "runs" / model / "full/history-inventory/repopilot"
        state = json.loads(next(folder.glob("run-state/*/checkpoint.json")).read_text())
        context = ContextManager()
        context.restore(state["context"])
        registry = create_tool_registry(LocalExecutionEnvironment(tmp_path), tmp_path, PlanHistory.for_task("check"))
        history = state["messages"]
        original = copy.deepcopy(history)
        tested = 0
        for i, m in enumerate(history):
            if i < 2 or m["role"] != "assistant":
                continue
            prepared = context.prepare(history[:i], state["plan"]).messages
            bounded = context.bound_request(prepared, registry.schemas)
            assert byte_size(bounded) + len(json.dumps(registry.schemas).encode()) + 4096 + 1024 <= 32768
            assert_protocol(bounded)
            assert "Only change src/inventory/*.py" in json.dumps(bounded)
            if bounded != prepared:
                records = receipts(bounded)
                assert any(
                    r["tool"] == "verify_task" and r.get("exit_code") == 1 and r.get("occurrence") == "first"
                    for r in records
                )
                # Six contracts fit alongside progress, even once their full outputs are gone.
                assert {r.get("path") for r in records if r["tool"] == "read_file"} >= {
                    f"docs/{name}.md"
                    for name in ["01-parse", "02-validate", "03-normalize", "04-aggregate", "05-select", "06-render"]
                }
                tested += 1
        assert tested > 30
        assert history == original
        restored = ContextManager()
        restored.restore(context.to_checkpoint())
        assert restored.bound_request(
            restored.prepare(history, state["plan"]).messages, registry.schemas
        ) == context.bound_request(context.prepare(history, state["plan"]).messages, registry.schemas)


def test_inventory_runtime_uses_retained_progress_to_edit_verify_and_finish(tmp_path):
    target = tmp_path / "target"
    fixture = EVIDENCE / "tasks/history-inventory"
    shutil.copytree(fixture / "snapshot", target)
    subprocess.run(["git", "init", "-q", str(target)], check=True)
    subprocess.run(["git", "add", "."], cwd=target, check=True)
    subprocess.run(
        ["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-qm", "seed"],
        cwd=target,
        check=True,
    )
    task = json.loads((fixture / "manifest.json").read_text())["task_statement"]
    solution = (EVIDENCE / "runs/gpt-5.6-sol/full/history-inventory/baseline/patch.diff").read_text()
    docs = sorted((target / "docs").glob("*.md"))

    class Model:
        model_name = "offline-context-progress"
        calls = 0

        def complete(self, messages, tools):
            self.calls += 1
            assert_protocol(messages)
            if self.calls == 1:
                return AssistantTurn(
                    tool_calls=[
                        ToolCall("start", "update_plan", {"step_id": "complete-task", "status": "IN_PROGRESS"}),
                        ToolCall(
                            "before",
                            "verify_task",
                            {
                                "command": "python -m unittest discover -s checks",
                                "check_id": "suite",
                                "scope": "inventory",
                                "reason": "before editing",
                            },
                        ),
                    ]
                )
            if self.calls == 2:
                return AssistantTurn(
                    tool_calls=[
                        ToolCall(f"read-{i}", "read_file", {"path": str(f.relative_to(target))})
                        for i, f in enumerate(docs + sorted((target / "src/inventory").glob("*.py")))
                    ]
                )
            if self.calls == 3:
                records = receipts(messages)
                assert any(r["tool"] == "verify_task" and r.get("exit_code") == 1 for r in records)
                contracts = [r for r in records if r.get("path", "").startswith("docs/")]
                assert len(contracts) == 6
                assert "casefold" in str(contracts) and "bool" in str(contracts)
                return AssistantTurn(tool_calls=[ToolCall("fix", "apply_patch", {"patch": solution})])
            if self.calls == 4:
                return AssistantTurn(
                    tool_calls=[
                        ToolCall(
                            "after",
                            "verify_task",
                            {
                                "command": "python -m unittest discover -s checks",
                                "check_id": "suite",
                                "scope": "inventory",
                                "reason": "after repair",
                                "step_ids": ["complete-task"],
                            },
                        )
                    ]
                )
            return AssistantTurn(
                tool_calls=[
                    ToolCall("done", "update_plan", {"step_id": "complete-task", "status": "COMPLETED"}),
                    ToolCall(
                        "finish",
                        "finish_task",
                        {"root_cause": "Stage stubs", "changes": ["Implemented stage contracts"]},
                    ),
                ]
            )

    model = Model()
    plan = PlanHistory.for_task(task)
    checks = []
    artifacts = RunArtifacts(tmp_path / "runs", secrets=[])
    result = AgentRuntime(
        model,
        create_tool_registry(LocalExecutionEnvironment(target), target, plan, verifications=checks),
        artifacts,
        plan,
        RunBudget(max_steps=8),
        verifications=checks,
    ).run(task, target)
    assert result.status == "SUCCEEDED"
    assert model.calls == 5
    assert (
        subprocess.run([sys.executable, str(fixture / "verify.py"), str(target)], capture_output=True).returncode == 0
    )
    calls = [e for e in artifacts.read_trace() if e["type"] == "tool_call"]
    assert sum(e["tool_name"] == "verify_task" for e in calls) == 2
