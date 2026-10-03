"""Audit completed #27 attempts without modifying historical experiment results."""

import hashlib
import json
import re
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
OLD = HERE.parent / "issue24-effective-ablation"


def read(path):
    return json.loads(path.read_text())


def lines(path):
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def main():
    rows = []
    for path in sorted(HERE.glob("round*/runs/*/history-inventory/repopilot/result.json")):
        folder = path.parent
        round_root = folder.parents[3]
        manifest = read(round_root / "source-manifest.json")
        result = read(path)
        model = folder.parents[1].name
        trace = lines(folder / "trace.jsonl")
        calls = [e for e in trace if e["type"] == "tool_call"]
        counts = dict(Counter(e["tool_name"] for e in calls))
        context = lines(folder / "context-events.jsonl")
        old = OLD / "runs" / model / "full/history-inventory/repopilot"
        old_result = read(old / "result.json") if (old / "result.json").exists() else None
        old_counts = dict(Counter(e["tool_name"] for e in lines(old / "trace.jsonl") if e["type"] == "tool_call"))
        patch = (folder / "patch.diff").read_bytes()
        changed = re.findall(r"^diff --git a/(.+) b/", patch.decode(), re.MULTILINE)
        patch_integrity = {}
        for name in ["patch-manifest.json", "runtime-patch-manifest.json"]:
            description = read(folder / name)
            raw = (folder / description.get("patch", "patch.diff")).read_bytes()
            patch_integrity[name] = (
                len(raw) == description["bytes"] and hashlib.sha256(raw).hexdigest() == description["sha256"]
            )
        metadata = read(folder / "metadata.json")
        verifications = []
        first_patch = next(
            (i for i, e in enumerate(trace) if e["type"] == "tool_call" and e.get("tool_name") == "apply_patch"),
            None,
        )
        for i, event in enumerate(trace):
            if event["type"] == "tool_result" and event.get("tool_name") in {"verify_task", "run_command"}:
                observation = event.get("observation", {}).get("result", {})
                verifications.append(
                    {
                        "trace_index": i,
                        "command": observation.get("command") or next((e.get("arguments", {}).get("command") for e in calls if e.get("tool_call_id") == event.get("tool_call_id")), None),
                        "exit_code": observation.get("result", observation).get("exit_code"),
                    }
                )
        rows.append(
            {
                "model": model,
                "round": round_root.name,
                "source_commit": manifest["commit"],
                "source_integrity": hashlib.sha256((round_root / "source.tar.gz").read_bytes()).hexdigest()
                == manifest["archive_sha256"],
                "experiment_integrity": all(
                    hashlib.sha256((round_root / p).read_bytes()).hexdigest() == sha
                    for p, sha in manifest["experiment_files"].items()
                ),
                "result_path": str(path.relative_to(HERE)),
                "status": result["status"],
                "repository_pass": result["success"],
                "task_pass": result["evaluation"]["task_pass"],
                "behavior_verifier": result["evaluation"].get("behavior_verifier"),
                "tool_counts": counts,
                "verifications": verifications,
                "failed_test_before_patch": first_patch is not None
                and any(v["trace_index"] < first_patch and v["exit_code"] == 1 for v in verifications),
                "successful_test_after_patch": first_patch is not None
                and any(v["trace_index"] > first_patch and v["exit_code"] == 0 for v in verifications),
                "read_paths": dict(Counter(e["arguments"].get("path") for e in calls if e["tool_name"] == "read_file")),
                "context_trim_requests": sum(e["context_changed"] for e in context),
                "requests_with_receipts": sum(bool(e["historical_receipts"]) for e in context),
                "instructions_always_present": bool(context)
                and all("AGENTS.md" in e["instruction_sources"] for e in context),
                "patch_bytes": len(patch),
                "changed_files": changed,
                "directory_constraint_pass": bool(changed)
                and all(re.fullmatch(r"src/inventory/[^/]+\.py", p) for p in changed),
                "patch_integrity": patch_integrity,
                "model_errors": sum(e["type"] == "model_response" and bool(e.get("error")) for e in trace),
                "empty_responses": sum(
                    e["type"] == "model_response"
                    and not e.get("error")
                    and not e.get("tool_calls")
                    and not (e.get("content") or "").strip()
                    for e in trace
                ),
                "failures": metadata.get("failures"),
                "metrics": {
                    k: result["metrics"].get(k)
                    for k in ["steps", "duration_seconds", "tokens", "cost", "retries", "run_budget"]
                },
                "old": None if old_result is None else {
                    "status": old_result["status"],
                    "repository_pass": old_result["success"],
                    "tool_counts": old_counts,
                    "patch_bytes": (old / "patch.diff").stat().st_size,
                },
            }
        )
    (HERE / "audit.json").write_text(
        json.dumps({"completed_runs": len(rows), "rows": rows}, indent=2, ensure_ascii=False) + "\n"
    )
    for r in rows:
        print(r["model"], r["status"], r["repository_pass"], r["task_pass"], r["tool_counts"])


if __name__ == "__main__":
    main()
