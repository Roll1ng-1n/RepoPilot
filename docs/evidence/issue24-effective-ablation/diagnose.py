"""Describe repeated exploration and baseline command-observer limitations."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main():
    rows = []
    for path in sorted((HERE / "runs").glob("*/*/*/*/result.json")):
        folder = path.parent
        trace_path = folder / "trace.jsonl"
        trace = [json.loads(line) for line in trace_path.read_text().splitlines()] if trace_path.exists() else []
        calls = [e for e in trace if e.get("type") == "tool_call"]
        row = {
            "result_path": str(path.relative_to(HERE)),
            "tool_counts": dict(Counter(e["tool_name"] for e in calls)),
            "read_paths": dict(Counter(e["arguments"].get("path") for e in calls if e["tool_name"] == "read_file")),
            "verification_commands": [e["arguments"].get("command") for e in calls if e["tool_name"] == "verify_task"],
        }
        checkpoints = list(folder.glob("run-state/*/checkpoint.json"))
        if checkpoints:
            checkpoint = json.loads(checkpoints[0].read_text())
            row["context_strategy"] = checkpoint["context"]["strategy"]
            row["context_summary"] = checkpoint["context"]["summary"]
            row["durable_facts"] = checkpoint["context"]["important_facts"]
            row["final_plan"] = checkpoint["plan"]
        trajectory_path = folder / "trajectory.json"
        if trajectory_path.exists():
            trajectory = json.loads(trajectory_path.read_text())
            messages = trajectory.get("messages", [])
            row["baseline_suite_commands"] = [
                c["function"]["arguments"]
                for m in messages
                for c in m.get("tool_calls", [])
                if "python -m unittest discover -s checks" in c.get("function", {}).get("arguments", "")
            ]
            row["baseline_test_outputs"] = [
                m.get("content")
                for m in messages
                if m.get("role") == "tool" and ("FAILED (" in str(m.get("content")) or "\nOK" in str(m.get("content")))
            ]
        rows.append(row)
    (HERE / "diagnostics.json").write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n")
    print("Diagnosed", len(rows), "runs")


if __name__ == "__main__":
    main()
