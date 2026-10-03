"""Print compact progress for active or completed real-model attempts."""

import json
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
for path in sorted(HERE.glob("round*/runs/*/history-inventory/repopilot/run-state/*/trace.jsonl")):
    events = []
    for line in path.read_text().splitlines():
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            break  # The writer may be appending the last record.
    counts = Counter(event["type"] for event in events)
    folder = path.parents[2]
    result = folder / "result.json"
    terminal = json.loads(result.read_text()) if result.exists() else {}
    print(
        json.dumps(
            {
                "round": path.parents[6].name,
                "model": path.parents[4].name,
                "requests": counts["model_request"],
                "responses": counts["model_response"],
                "tool_counts": dict(Counter(e["tool_name"] for e in events if e["type"] == "tool_call")),
                "model_errors": sum(e["type"] == "failure" and e.get("category") == "MODEL_ERROR" for e in events),
                "last_event": events[-1]["type"] if events else None,
                "status": terminal.get("status", "RUNNING"),
                "repository_pass": terminal.get("success"),
            }
        )
    )
