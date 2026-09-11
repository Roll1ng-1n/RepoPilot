"""Read-only audit of pinned experiment inputs and completed run artifacts."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def read(path):
    return json.loads(path.read_text()) if path.exists() else {}


def main():
    replacement = len(sys.argv) > 1
    runs_root = HERE / (sys.argv[1] if replacement else "runs")
    pinned = read(HERE / "source-manifest.json")
    integrity = all(
        hashlib.sha256((HERE / name).read_bytes()).hexdigest() == sha
        for name, sha in pinned["experiment_files"].items()
    )
    integrity &= hashlib.sha256((HERE / "source.tar.gz").read_bytes()).hexdigest() == pinned["archive_sha256"]
    rows = []
    for path in sorted(runs_root.glob("*/*/*/*/result.json")):
        model, variant, task, engine, _ = path.relative_to(runs_root).parts
        result = read(path)
        metrics = result["metrics"]
        folder = path.parent
        source_reference = read(folder.parent.parent / "source-reference.json")
        events_path = folder / "variant-events.jsonl"
        events = [json.loads(line) for line in events_path.read_text().splitlines()] if events_path.exists() else []
        patches = {}
        for name in ["patch-manifest.json", "runtime-patch-manifest.json"]:
            manifest = read(folder / name)
            if manifest:
                patch = folder / manifest.get("patch", "patch.diff")
                raw = patch.read_bytes()
                patches[name] = len(raw) == manifest["bytes"] and hashlib.sha256(raw).hexdigest() == manifest["sha256"]
        metadata = read(folder / "metadata.json")
        trace_path = folder / "trace.jsonl"
        trace = [json.loads(line) for line in trace_path.read_text().splitlines()] if trace_path.exists() else []
        rows.append(
            {
                "model": model,
                "arm": "baseline" if engine == "baseline" else variant,
                "task": task,
                "run_id": result["run_id"],
                "status": result["status"],
                "repository_pass": result["success"],
                "task_pass": result["evaluation"]["task_pass"],
                "termination": result["evaluation"].get("termination"),
                "recovery_evaluation": result["evaluation"].get("recovery"),
                "error": result["error"],
                "source_reference_matches": all(
                    source_reference.get(k) == pinned[k]
                    for k in ["archive_sha256", "experiment_files_sha256"]
                ),
                "budget_matches": metrics.get("run_budget") == read(HERE / "evaluation-plan.json")["budgets"],
                "tokens": metrics.get("tokens"),
                "cost": metrics.get("cost"),
                "estimated_cost_usd": metrics.get("openai_standard_estimated_cost_usd"),
                "duration_seconds": metrics.get("duration_seconds"),
                "steps": metrics.get("steps"),
                "recoveries": metadata.get("recoveries"),
                "failures": metadata.get("failures"),
                "budget_exhaustion": [e.get("limit") for e in trace if e.get("type") == "budget_exhausted"],
                "usage_incomplete": bool(metadata.get("budget", {}).get("unknown_tokens")) if metadata else None,
                "cost_incomplete": bool(metadata.get("budget", {}).get("unknown_cost")) if metadata else None,
                "model_error_responses": sum(e.get("type") == "model_response" and bool(e.get("error")) for e in trace)
                if metadata
                else None,
                "blank_model_responses": sum(
                    e.get("type") == "model_response"
                    and not e.get("error")
                    and not e.get("tool_calls")
                    and not (e.get("content") or "").strip()
                    for e in trace
                )
                if metadata
                else None,
                "retries": metrics.get("retries"),
                "replans": metrics.get("replans"),
                "patch_integrity": patches,
                "profile_fact_counts": sorted({e["profile_fact_count"] for e in events}),
                "planning_enabled": sorted({e["planning_enabled"] for e in events}),
                "instruction_sources": sorted({s for e in events for s in e["instruction_sources"]}),
                "planning_calls": [
                    e for e in trace if e.get("type") == "tool_call" and e.get("tool_name") in {"update_plan", "replan"}
                ],
                "context_trim_requests": sum(bool(e.get("context_changed")) for e in events),
                "context_limit_requests": sum(bool(e.get("context_limit_reached")) for e in events),
                "max_input_bytes": max((e["input_bytes_before"] for e in events), default=None),
                "telemetry_requests": len(events),
                "trace_events": len(trace),
                "result_path": str(path.relative_to(HERE)),
            }
        )
    violations = []
    for row in rows:
        identity = f"{row['model']}/{row['arm']}/{row['task']}"
        if not row["source_reference_matches"] or not row["budget_matches"]:
            violations.append(identity + ": source reference or budget mismatch")
        expected_patches = 1 if row["arm"] == "baseline" else 2
        if len(row["patch_integrity"]) != expected_patches or not all(row["patch_integrity"].values()):
            violations.append(identity + ": missing or mismatched patch manifest")
        if row["arm"] == "baseline":
            continue
        if not row["telemetry_requests"] or "AGENTS.md" not in row["instruction_sources"]:
            violations.append(identity + ": missing runtime telemetry or root instructions")
        if row["profile_fact_counts"] != ([0] if row["arm"] == "no-profile" else [1]):
            violations.append(identity + ": profile switch mismatch")
        if row["planning_enabled"] != [row["arm"] != "no-planning"]:
            violations.append(identity + ": planning switch mismatch")
        if row["arm"] == "no-planning" and row["planning_calls"]:
            violations.append(identity + ": planning tool called while disabled")
        if row["arm"] == "no-context-selection" and row["context_trim_requests"]:
            violations.append(identity + ": context trimmed while disabled")
    report = {
        "input_integrity": bool(integrity),
        "completed_runs": len(rows),
        "expected_runs": read(HERE / "replacement-plan.json")["selected_count"] if replacement else 24,
        "unique_run_ids": len({r["run_id"] for r in rows}) == len(rows),
        "violations": violations,
        "rows": rows,
    }
    (HERE / ("replacement-audit.json" if replacement else "audit.json")).write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    )
    print(json.dumps({k: v for k, v in report.items() if k != "rows"}))
    for row in rows:
        print(
            row["model"],
            row["arm"],
            row["task"],
            row["status"],
            row["repository_pass"],
            row["task_pass"],
            "trim",
            row["context_trim_requests"],
        )


if __name__ == "__main__":
    main()
