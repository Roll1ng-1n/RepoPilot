"""Explicit paid execution of the precommitted #31/#32 plan, using frozen source."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tarfile
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent


def read(path):
    return json.loads(path.read_text())


def provider_failure(directory):
    traces = list(directory.glob("*/**/trace.jsonl"))
    for path in traces:
        for line in path.read_text().splitlines():
            event = json.loads(line)
            if event.get("type") == "model_response" and event.get("error"):
                text = str(event["error"]).lower()
                if any(
                    word in text
                    for word in (
                        "timeout",
                        "connection",
                        "ratelimit",
                        "internalserver",
                        "truncated",
                        "protocol",
                        "503",
                        "502",
                    )
                ):
                    return True
            if (
                event.get("type") == "model_response"
                and not event.get("error")
                and not event.get("tool_calls")
                and not (event.get("content") or "").strip()
            ):
                return True
    for path in directory.glob("*/**/result.json"):
        result = read(path)
        text = str(result.get("error") or "").lower()
        if any(word in text for word in ("timeout", "connection", "ratelimit", "internalserver", "503", "502")):
            return True
    return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True, choices=["gpt-6.1-sol", "gpt-6-luna"])
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--execute", action="store_true", help="Explicitly allow model calls")
    args = parser.parse_args()
    if not args.execute:
        raise SystemExit("No model calls: pass --execute after reviewing evaluation-plan.json.")
    manifest = read(HERE / "source-manifest.json")
    plan = read(HERE / "evaluation-plan.json")
    archive = HERE / "source.tar.gz"
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == manifest["archive_sha256"]
    for filename, digest in manifest["experiment_files"].items():
        assert hashlib.sha256((HERE / filename).read_bytes()).hexdigest() == digest, filename
    with tempfile.TemporaryDirectory(prefix="repopilot-fixed-models-") as temporary:
        source = Path(temporary)
        with tarfile.open(archive) as tar:
            tar.extractall(source, filter="data")
        for filename, digest in manifest["files"].items():
            assert hashlib.sha256((source / filename).read_bytes()).hexdigest() == digest, filename
        sys.path.insert(0, str(source / "src"))
        from dotenv import dotenv_values

        import repopilot.benchmark as b

        values = dotenv_values(args.env_file)
        if not values.get("REPOPILOT_API_KEY"):
            raise SystemExit("Missing REPOPILOT_API_KEY")
        model = b.BenchmarkModel(
            "openai/" + args.model,
            api_key=values["REPOPILOT_API_KEY"],
            base_url=values.get("REPOPILOT_BASE_URL") or "https://jojocode.com/v1",
            model_kwargs=plan["model_kwargs"],
        )
        root = HERE / "runs" / args.model
        root.mkdir(parents=True, exist_ok=True)

        def attempt(stage, repeat, task, variant, replacement=False):
            name = f"{stage}-{repeat:02d}-{task}-{variant}" + ("-replacement" if replacement else "")
            output = root / name
            completed = output / "trial.json"
            if completed.exists():
                return read(completed)
            if output.exists():
                raise RuntimeError(f"Incomplete existing trial preserved: {output}")
            config = b.BenchmarkConfig(
                tasks_directory=HERE / "tasks",
                output_directory=output,
                model=model,
                image=plan["image"],
                budget=b.BenchmarkBudget(**plan["budgets"]),
                engines=("baseline" if variant == "baseline" else "repopilot",),
                task_ids=(task,),
                repeats=1,
                progress_detection_enabled=variant != "loop-off",
            )
            result = b.run_benchmark(config).results[0].to_dict()
            record = {
                "stage": stage,
                "repeat": repeat,
                "replacement": replacement,
                "variant": variant,
                "source_sha256": manifest["archive_sha256"],
                "result": result,
                "provider_failure": provider_failure(output),
            }
            completed.write_text(json.dumps(record, indent=2) + "\n")
            print(
                args.model,
                name,
                result.get("status"),
                result.get("repository_pass"),
                result.get("task_pass"),
                flush=True,
            )
            return record

        smoke = attempt("smoke", 0, plan["tasks"][0], "loop-on")
        if smoke["result"].get("status") != "SUCCEEDED" and smoke["provider_failure"]:
            smoke = attempt("smoke", 0, plan["tasks"][0], "loop-on", replacement=True)
        if smoke["result"].get("status") is None or smoke["result"].get("repository_pass") is not True:
            raise RuntimeError(
                "Smoke did not establish functional execution; trials preserved, formal campaign not started."
            )
        for repeat in range(1, plan["repeats"] + 1):
            variants = plan["variants"][repeat - 1 :] + plan["variants"][: repeat - 1]
            for task in plan["tasks"]:
                for variant in variants:
                    record = attempt("formal", repeat, task, variant)
                    result = record["result"]
                    if record["provider_failure"] and (
                        result.get("status") not in {"SUCCEEDED", "Submitted"} or result.get("task_pass") is not True
                    ):
                        attempt("formal", repeat, task, variant, replacement=True)
        (root / "completed.json").write_text(json.dumps({"model": args.model, "formal_plan_completed": True}) + "\n")


if __name__ == "__main__":
    main()
