"""Audit completed round3 artifacts without rerunning model requests."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main():
    manifest = json.loads((HERE / "source-manifest.json").read_text())
    for name, key in (("source.tar.gz", "archive_sha256"), ("run_real_models.py", "runner_sha256")):
        assert hashlib.sha256((HERE / name).read_bytes()).hexdigest() == manifest[key]
    results = []
    audits = []
    for stage in ("smoke", "no-planning"):
        for model in ("gpt-5.6-sol", "gpt-5.6-luna"):
            directory = HERE / stage / model
            assert (directory / "summary.json").exists(), directory
            reference = json.loads((directory / "source-reference.json").read_text())
            assert reference["archive_sha256"] == manifest["archive_sha256"]
            assert reference["runner_sha256"] == manifest["runner_sha256"]
            assert reference["planning_enabled"] == (stage == "smoke")
            for task in ("seed-single-file", "recovery-public-failure"):
                for engine in (("baseline", "repopilot") if stage == "smoke" else ("repopilot",)):
                    path = directory / task / engine / "result.json"
                    result = json.loads(path.read_text())
                    assert (result["task_id"], result["engine"], result["model"]) == (task, engine, "openai/" + model)
                    assert result["error"] is None
                    assert result["task_pass"] == (result["repository_pass"] and result["behavior_pass"])
                    assert result["repository_pass"] == (result["verifier"]["exit_code"] == 0)
                    metrics = result["metrics"]
                    assert metrics["run_budget"]["max_run_seconds"] == 180
                    assert metrics["run_budget"]["max_steps"] == 15
                    patch = metrics["patch"]
                    assert hashlib.sha256(Path(patch["path"]).read_bytes()).hexdigest() == patch["sha256"]
                    audit = {"sample": str(path.relative_to(HERE)), "patch_hash_verified": True}
                    if engine == "repopilot":
                        events = [json.loads(line) for line in path.with_name("trace.jsonl").read_text().splitlines()]
                        assert events[-1]["type"] == "run_finished"
                        assert events[-1]["status"] == result["status"]
                        recoveries = [event for event in events if event["type"] == "recovery"]
                        assert metrics["retries"] == sum(event["action"] == "RETRY_MODEL" for event in recoveries)
                        calls = [event for event in events if event["type"] == "tool_call"]
                        audit["recoveries"] = recoveries
                        audit["budget_exhausted"] = [event.get("limit") for event in events if event["type"] == "budget_exhausted"]
                        if stage == "no-planning":
                            assert not any(event["tool_name"] in ("create_plan", "update_plan", "replan") for event in calls)
                            verification = [event for event in calls if event["tool_name"] == "verify_task"]
                            assert verification
                            assert all("step_ids" not in event["arguments"] for event in verification)
                            audit["verification_without_step_ids"] = True
                    results.append({"stage": stage, **result})
                    audits.append(audit)
    assert len(results) == 12
    assert len({result["run_id"] for result in results}) == 12
    (HERE / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n")
    (HERE / "result-audit.json").write_text(json.dumps({
        "sample_count": len(results), "unique_run_ids": True,
        "source_archive_sha256": manifest["archive_sha256"], "samples": audits,
    }, ensure_ascii=False, indent=2) + "\n")
    for result in results:
        print(result["stage"], result["model"], result["task_id"], result["engine"], result["status"], result["task_pass"])


if __name__ == "__main__":
    main()
