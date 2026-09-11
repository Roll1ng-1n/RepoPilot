"""Validate seed/solution contrast and experimental switches without model calls."""

import ast
import copy
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from variants import VARIANTS, variant_context

import repopilot.benchmark as b
import repopilot.runtime as runtime
from repopilot.benchmark import load_tasks
from repopilot.budget import BudgetExceeded
from repopilot.environment import LocalExecutionEnvironment
from repopilot.plan import PlanHistory
from repopilot.recovery import Failure, FailureCategory, RecoveryAction, RecoveryController

HERE = Path(__file__).resolve().parent
solutions = {
    "profile-ledger": {
        "src/ledger/normalize.py": "def normalize_key(key: str) -> str:\n    return key.strip().casefold()\n",
        "src/ledger/report.py": """from decimal import Decimal, ROUND_HALF_UP
from .normalize import normalize_key
def report(rows: list[tuple[str, str]]) -> str:
    totals={}
    for key, amount in rows:
        key=normalize_key(key)
        if key: totals[key]=totals.get(key,Decimal(0))+Decimal(amount)
    return '\\n'.join(f'{key}={totals[key].quantize(Decimal("0.01"), rounding=ROUND_HALF_UP):.2f}' for key in sorted(totals))
""",
    },
    "history-inventory": {
        "parse": "import json\ndef parse(text: str):\n    try: value=json.loads(text)\n    except (ValueError,TypeError): return []\n    return value if isinstance(value,list) else []\n",
        "validate": 'def validate(events: list):\n    return [{"sku":e["sku"],"delta":e["delta"]} for e in events if isinstance(e,dict) and isinstance(e.get("sku"),str) and e["sku"].strip() and type(e.get("delta")) is int]\n',
        "normalize": 'def normalize(events: list):\n    return [{"sku":e["sku"].strip().casefold(),"delta":e["delta"]} for e in events]\n',
        "aggregate": 'def aggregate(events: list):\n    out={}\n    for e in events: out[e["sku"]]=out.get(e["sku"],0)+e["delta"]\n    return out\n',
        "select": "def select(balances: dict):\n    return {k:v for k,v in balances.items() if v != 0}\n",
        "render": 'def render(balances: dict):\n    return "\\n".join(f"{k}={balances[k]}" for k in sorted(balances))\n',
    },
}


def main():
    records = []
    for task in load_tasks(HERE / "tasks"):
        for p in task.snapshot.rglob("*.py"):
            ast.parse(p.read_text())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "workspace"
            shutil.copytree(task.snapshot, root)
            command = [sys.executable, str(HERE / "tasks" / task.task_id / "verify.py"), str(root)]
            seed = subprocess.run(command, capture_output=True).returncode
            assert seed != 0
            public = subprocess.run(
                [sys.executable, "-m", "unittest", "discover", "-s", "checks"], cwd=root, capture_output=True
            ).returncode
            assert public != 0
            for name, code in solutions[task.task_id].items():
                path = root / (name if "/" in name else f"src/inventory/{name}.py")
                path.write_text(code)
            for cache in root.rglob("__pycache__"):
                shutil.rmtree(cache)
            solved = subprocess.run(command, capture_output=True, text=True)
            assert solved.returncode == 0, solved.stderr
            assert (
                subprocess.run(
                    [sys.executable, "-m", "unittest", "discover", "-s", "checks"], cwd=root, capture_output=True
                ).returncode
                == 0
            )
            records.append({"task": task.task_id, "seed_verifier": seed, "seed_public": public, "solution_verifier": 0})
    root = HERE / "tasks" / "profile-ledger" / "snapshot"
    for variant in VARIANTS:
        with variant_context(variant, None):
            profile = runtime.repository_profile(root.resolve())
            assert bool(profile["facts"]) == (variant != "no-profile")
            assert profile["instructions"]
            reg = b.create_tool_registry(LocalExecutionEnvironment(root), root, PlanHistory.for_task("check"))
            names = [s["function"]["name"] for s in reg.schemas]
            assert ("update_plan" in names) == (variant != "no-planning")
            if variant == "no-planning":
                assert "step_ids" not in next(
                    s["function"]["parameters"]["properties"]
                    for s in reg.schemas
                    if s["function"]["name"] == "verify_task"
                )
            decision = RecoveryController(5).recover(Failure(FailureCategory.VERIFICATION_FAILURE, "expected"))
            assert (decision.action is RecoveryAction.STOP) == (variant == "no-recovery")
            assert (
                RecoveryController(5)
                .recover(Failure(FailureCategory.MODEL_ERROR, "timeout"), transient_model_error=True)
                .action
                is RecoveryAction.RETRY_MODEL
            )
            history = [{"role": "system", "content": "required"}, {"role": "user", "content": "task"}]
            for i in range(8):
                history.extend(
                    [
                        {
                            "role": "assistant",
                            "tool_calls": [
                                {"id": str(i), "type": "function", "function": {"name": "read_file", "arguments": "{}"}}
                            ],
                        },
                        {"role": "tool", "tool_call_id": str(i), "content": "contract example " + ("x" * 6000)},
                    ]
                )
            context = b.ContextManager()
            failure_limit = None
            try:
                selected = context.bound_request(copy.deepcopy(history), reg.schemas)
                assert variant != "no-context-selection"
                assert len(selected) < len(history)
                ids = {c["id"] for m in selected for c in m.get("tool_calls", [])}
                assert ids == {m["tool_call_id"] for m in selected if m.get("role") == "tool"}
            except BudgetExceeded as e:
                failure_limit = e.limit
            assert failure_limit == ("context_window" if variant == "no-context-selection" else None)
            records.append(
                {
                    "variant": variant,
                    "profile_facts": len(profile["facts"]),
                    "planning": reg.planning_enabled,
                    "task_recovery": decision.action.value,
                    "transport_retry_preserved": True,
                    "long_history_switch_verified": True,
                }
            )
    (HERE / "offline-checks.json").write_text(json.dumps(records, indent=2) + "\n")
    print(json.dumps(records, indent=2))


if __name__ == "__main__":
    main()
