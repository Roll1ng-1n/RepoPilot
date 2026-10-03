"""Read-only campaign progress, without a provider call or artifact rewrite."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main():
    rows = []
    for folder in sorted((HERE / "runs/gpt-6.1-sol").iterdir()):
        if not folder.is_dir():
            continue
        completed = folder / "trial.json"
        if completed.exists():
            record = json.loads(completed.read_text())
            result = record["result"]
            rows.append(
                {
                    "trial": folder.name,
                    "complete": True,
                    "replacement": record["replacement"],
                    "status": result.get("status"),
                    "repository_pass": result.get("repository_pass"),
                    "task_pass": result.get("task_pass"),
                    "steps": result.get("metrics", {}).get("steps"),
                }
            )
            continue
        traces = list(folder.glob("*/repopilot/run-state/*/trace.jsonl"))
        trajectories = list(folder.glob("*/baseline/trajectory.json"))
        row = {"trial": folder.name, "complete": False}
        if traces:
            trace = traces[0]
            events = []
            for line in trace.read_text().splitlines():
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    break  # A writer may currently be appending the last record.
            requests = [e for e in events if e.get("type") == "model_request"]
            failures = [e for e in events if e.get("type") == "failure"]
            row.update(
                requests=len(requests),
                step=requests[-1].get("step") if requests else None,
                failures=len(failures),
                last_event=events[-1].get("type") if events else None,
                last_trace_utc=datetime.fromtimestamp(trace.stat().st_mtime, timezone.utc).isoformat(),
            )
        elif trajectories:
            row["last_trajectory_utc"] = datetime.fromtimestamp(
                trajectories[0].stat().st_mtime, timezone.utc
            ).isoformat()
        rows.append(row)
    count = sum(row["complete"] and row["trial"].startswith("formal-") and not row["replacement"] for row in rows)
    print(
        json.dumps(
            {
                "formal_originals": count,
                "expected": 45,
                "completed_marker": (HERE / "runs/gpt-6.1-sol/completed.json").exists(),
                "rows": rows,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
