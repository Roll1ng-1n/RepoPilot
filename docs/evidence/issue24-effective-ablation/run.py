"""Pinned two-model, two-task smoke followed by four isolated ablations."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tarfile
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
IMAGE = "sha256:67ecd4d89a62e76c2a6eabaabea62a9499ccf356cd310efa5495b43a6e2eedb6"
TASKS = ("profile-ledger", "history-inventory")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", choices=["gpt-5.6-sol", "gpt-5.6-luna"], required=True)
    parser.add_argument("--stage", choices=["smoke", "ablation"], required=True)
    parser.add_argument("--env-file", type=Path, required=True)
    args = parser.parse_args()
    pinned = json.loads((HERE / "source-manifest.json").read_text())
    for relative, expected in pinned["experiment_files"].items():
        assert hashlib.sha256((HERE / relative).read_bytes()).hexdigest() == expected, relative
    archive = HERE / "source.tar.gz"
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == pinned["archive_sha256"]
    with tempfile.TemporaryDirectory(prefix="issue24-pinned-") as temporary:
        source = Path(temporary)
        with tarfile.open(archive) as tar:
            tar.extractall(source, filter="data")
        for relative, expected in pinned["files"].items():
            assert hashlib.sha256((source / relative).read_bytes()).hexdigest() == expected, relative
        sys.path.insert(0, str(source / "src"))
        from dotenv import dotenv_values
        from variants import variant_context

        import repopilot.benchmark as b

        values = dotenv_values(args.env_file)
        key = values.get("REPOPILOT_API_KEY")
        base_url = values.get("REPOPILOT_BASE_URL") or "https://jojocode.com/v1"
        if not key:
            raise SystemExit("Missing REPOPILOT_API_KEY")
        variants = (
            ["full"] if args.stage == "smoke" else ["no-profile", "no-context-selection", "no-planning", "no-recovery"]
        )
        if args.model.endswith("luna") and args.stage == "ablation":
            variants.reverse()
        for variant in variants:
            output = HERE / "runs" / args.model / variant
            if (output / "summary.json").exists():
                print("SKIP complete", args.model, variant, flush=True)
                continue
            if output.exists():
                raise SystemExit("Preserve interrupted output before retry: " + str(output))
            if args.stage == "ablation" and not (HERE / "runs" / args.model / "full" / "summary.json").exists():
                raise SystemExit("Smoke must finish before ablation")
            output.mkdir(parents=True)
            (output / "source-reference.json").write_text(
                json.dumps(
                    {
                        "archive_sha256": pinned["archive_sha256"],
                        "variant": variant,
                        "experiment_files_sha256": pinned["experiment_files_sha256"],
                    },
                    indent=2,
                )
                + "\n"
            )
            config = b.BenchmarkConfig(
                tasks_directory=HERE / "tasks",
                output_directory=output,
                repeats=1,
                task_ids=TASKS,
                engines=("baseline", "repopilot") if variant == "full" else ("repopilot",),
                model=b.BenchmarkModel(
                    "openai/" + args.model,
                    api_key=key,
                    base_url=base_url,
                    model_kwargs={"temperature": 1, "stream": True, "timeout": 120, "max_tokens": 4096},
                ),
                image=IMAGE,
                budget=b.BenchmarkBudget(
                    max_steps=48,
                    max_replans=4,
                    max_consecutive_failures=5,
                    command_timeout_seconds=60,
                    max_run_seconds=7200,
                ),
            )

            def execute(request):
                with variant_context(variant, request.artifact_directory / "variant-events.jsonl"):
                    return b._run_repopilot(request)

            print("START", args.model, variant, flush=True)
            result = b.run_benchmark(
                config, executors={"repopilot": execute}, preflight_runner=b.preflight_benchmark_image
            )
            for row in result.results:
                print(
                    json.dumps(
                        {
                            "model": args.model,
                            "variant": variant,
                            "task": row.task_id,
                            "engine": row.engine.value,
                            "status": row.status,
                            "task_pass": row.evaluation.get("task_pass"),
                            "repository_pass": row.success,
                            "error": row.error,
                        }
                    ),
                    flush=True,
                )
            print("DONE", args.model, variant, flush=True)


if __name__ == "__main__":
    main()
