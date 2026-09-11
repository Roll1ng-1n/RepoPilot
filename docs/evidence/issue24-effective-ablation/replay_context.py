"""Offline replay of retained history prefixes; no model requests or repository edits."""

import json
from pathlib import Path

from repopilot.context import ContextManager
from repopilot.environment import LocalExecutionEnvironment
from repopilot.plan import PlanHistory
from repopilot.tools import create_tool_registry

HERE = Path(__file__).resolve().parent


def main():
    rows = []
    for model in ["gpt-5.6-sol", "gpt-5.6-luna"]:
        root = HERE / "runs" / model / "full" / "history-inventory" / "repopilot"
        checkpoint = json.loads(next(root.glob("run-state/*/checkpoint.json")).read_text())
        context = ContextManager()
        context.restore(checkpoint["context"])
        workspace = root / "workspace"
        registry = create_tool_registry(
            LocalExecutionEnvironment(workspace), workspace, PlanHistory.for_task(checkpoint["task"])
        )
        messages = checkpoint["messages"]
        prefixes = []
        for i, message in enumerate(messages):
            if i < 2 or message["role"] != "assistant":
                continue
            before = context.prepare(messages[:i], checkpoint["plan"]).messages
            after = context.bound_request(before, registry.schemas)
            before_calls = {c["id"]: c["function"] for m in before for c in m.get("tool_calls", [])}
            after_ids = {c["id"] for m in after for c in m.get("tool_calls", [])}
            removed = [c for k, c in before_calls.items() if k not in after_ids]
            prefixes.append(
                {
                    "history_prefix_length": i,
                    "retained_messages": len(after),
                    "removed_verify_calls": sum(c["name"] == "verify_task" for c in removed),
                    "removed_doc_reads": sum(c["name"] == "read_file" and "docs/" in c["arguments"] for c in removed),
                    "retained_tool_names": [before_calls[k]["name"] for k in before_calls if k in after_ids],
                }
            )
        rows.append(
            {
                "model": model,
                "note": "Replays retained message prefixes using final checkpoint profile/plan. This is an offline mechanism diagnosis, not exact historical request capture.",
                "prefixes": prefixes,
            }
        )
    (HERE / "context-replay.json").write_text(json.dumps(rows, indent=2) + "\n")
    print("Replayed", sum(len(r["prefixes"]) for r in rows), "history prefixes without model calls")


if __name__ == "__main__":
    main()
