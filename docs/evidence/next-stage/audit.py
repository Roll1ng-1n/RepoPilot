"""Offline audit of frozen inputs, trial identities, configuration, and raw evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import tarfile
from pathlib import Path

from run_models import provider_failure

HERE = Path(__file__).resolve().parent


def read(path):
    return json.loads(path.read_text())


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--require-complete", action="store_true")
    args = parser.parse_args()
    plan = read(HERE / "evaluation-plan.json")
    amendment = read(HERE / "plan-amendment.json")
    manifest = read(HERE / "source-manifest.json")
    assert sha256(HERE / "source.tar.gz") == manifest["archive_sha256"]
    with tarfile.open(HERE / "source.tar.gz") as archive:
        for name, expected in manifest["files"].items():
            member = archive.extractfile(name)
            assert member is not None, name
            assert hashlib.sha256(member.read()).hexdigest() == expected, name
    for name, expected in manifest["experiment_files"].items():
        assert sha256(HERE / name) == expected, name

    originals = {}
    replacements = []
    trial_paths = sorted((HERE / "runs").glob("*/*/trial.json"))
    for path in trial_paths:
        trial = read(path)
        result = trial["result"]
        config = read(path.parent / "config.json")
        model = path.parents[1].name
        task = result["task_id"]
        variant = trial["variant"]
        expected_name = f"{trial['stage']}-{trial['repeat']:02d}-{task}-{variant}"
        if trial["replacement"]:
            expected_name += "-replacement"
        assert path.parent.name == expected_name, path
        assert trial["source_sha256"] == manifest["archive_sha256"], path
        assert trial["provider_failure"] == provider_failure(path.parent), path
        assert config["budget"] == plan["budgets"], path
        assert config["image"] == config["image_id"] == plan["image"], path
        assert config["model"]["model_name"] == "openai/" + model, path
        assert config["model"]["model_kwargs"] == plan["model_kwargs"], path
        assert config["progress_detection_enabled"] == (variant != "loop-off"), path
        assert config["task_ids"] == [task] and config["repeats"] == 1, path
        engine = "baseline" if variant == "baseline" else "repopilot"
        assert config["engines"] == [engine] and result["engine"] == engine, path
        raw_result = read(path.parent / task / engine / "result.json")
        for field in ("status", "repository_pass", "task_pass"):
            assert raw_result.get(field) == result.get(field), (path, field)
        key = (model, trial["stage"], trial["repeat"], task, variant)
        if trial["replacement"]:
            replacements.append((key, path))
        else:
            assert key not in originals, key
            originals[key] = trial

    replacement_keys = [key for key, _ in replacements]
    assert len(replacement_keys) == len(set(replacement_keys)), "Duplicate replacements"
    for key, path in replacements:
        original = originals[key]
        result = original["result"]
        assert original["provider_failure"], path
        assert result.get("status") not in {"SUCCEEDED", "Submitted"} or result.get("task_pass") is not True, path

    planned = {
        (model, "formal", repeat, task, variant)
        for model in amendment["active_models"]
        for repeat in range(1, plan["repeats"] + 1)
        for task in plan["tasks"]
        for variant in plan["variants"]
    }
    observed = {key for key in originals if key[1] == "formal"}
    assert observed <= planned, "Unplanned formal original"
    markers = all((HERE / "runs" / model / "completed.json").exists() for model in amendment["active_models"])
    complete = observed == planned and markers
    report = {
        "complete": complete,
        "formal_originals": len(observed),
        "expected_formal_originals": len(planned),
        "missing": [list(key) for key in sorted(planned - observed)],
        "trial_records": len(trial_paths),
        "replacements": len(replacements),
        "archive_sha256": manifest["archive_sha256"],
        "source_files_verified": len(manifest["files"]),
        "experiment_files_verified": len(manifest["experiment_files"]),
        "scope": "No model calls. Checks input hashes, identities, image/model/budgets, raw terminal results, and replacement eligibility. Does not establish causal effects of provider errors.",
    }
    if args.require_complete:
        assert complete, "Campaign is incomplete"
        evidence = {}
        for path in sorted((HERE / "runs").rglob("*")):
            relative = path.relative_to(HERE / "runs")
            if not path.is_file() or any(part in {"workspace", ".git", "__pycache__", ".pytest_cache"} for part in relative.parts):
                continue
            if path.name == "run.lock":
                continue
            evidence[str(path.relative_to(HERE))] = sha256(path)
        (HERE / "raw-evidence-manifest.json").write_text(json.dumps(evidence, indent=2) + "\n")
        report["raw_evidence_files"] = len(evidence)
        report["raw_evidence_manifest_sha256"] = sha256(HERE / "raw-evidence-manifest.json")
        (HERE / "audit.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
