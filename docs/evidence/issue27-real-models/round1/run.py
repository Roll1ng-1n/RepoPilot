"""Pinned real-model acceptance runs for #27; never overwrite a prior attempt."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tarfile
import tempfile
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", choices=["gpt-5.6-sol", "gpt-5.6-luna"], required=True)
    parser.add_argument("--env-file", type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads((HERE / "source-manifest.json").read_text())
    plan = json.loads((HERE / "evaluation-plan.json").read_text())
    for name, digest in manifest["experiment_files"].items():
        assert hashlib.sha256((HERE / name).read_bytes()).hexdigest() == digest, name
    archive = HERE / "source.tar.gz"
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == manifest["archive_sha256"]
    output = HERE / "runs" / args.model
    if output.exists():
        raise SystemExit("Refusing to overwrite an existing attempt: " + str(output))
    with tempfile.TemporaryDirectory(prefix="issue27-pinned-") as temporary:
        source = Path(temporary)
        with tarfile.open(archive) as tar:
            tar.extractall(source, filter="data")
        for name, digest in manifest["files"].items():
            assert hashlib.sha256((source / name).read_bytes()).hexdigest() == digest, name
        sys.path.insert(0, str(source / "src"))
        from dotenv import dotenv_values

        import repopilot.benchmark as b
        from repopilot.context import ContextManager

        values = dotenv_values(args.env_file)
        if not values.get("REPOPILOT_API_KEY"):
            raise SystemExit("Missing REPOPILOT_API_KEY")
        config = b.BenchmarkConfig(
            tasks_directory=HERE / "tasks",
            output_directory=output,
            repeats=1,
            task_ids=("history-inventory",),
            engines=("repopilot",),
            model=b.BenchmarkModel(
                "openai/" + args.model,
                api_key=values["REPOPILOT_API_KEY"],
                base_url=values.get("REPOPILOT_BASE_URL") or "https://jojocode.com/v1",
                model_kwargs=plan["model_kwargs"],
            ),
            image=plan["image"],
            budget=b.BenchmarkBudget(**plan["budgets"]),
        )

        def execute(request):
            class ObservedContext(ContextManager):
                def bound_request(self, messages, schemas):
                    selected = super().bound_request(messages, schemas)
                    receipts = [
                        m["content"]
                        for m in selected
                        if isinstance(m.get("content"), str) and m["content"].startswith("Historical tool receipts")
                    ]
                    event = {
                        "context_changed": selected != messages,
                        "messages_before": len(messages),
                        "messages_after": len(selected),
                        "input_bytes_before": len(json.dumps(messages, ensure_ascii=False).encode()),
                        "input_bytes_after": len(json.dumps(selected, ensure_ascii=False).encode()),
                        "historical_receipts": receipts,
                        "instruction_sources": [
                            i["source"] for i in (self.repository_profile or {}).get("instructions", [])
                        ],
                    }
                    with (request.artifact_directory / "context-events.jsonl").open("a") as stream:
                        stream.write(json.dumps(event, ensure_ascii=False) + "\n")
                    return selected

            with patch.object(b, "ContextManager", ObservedContext):
                return b._run_repopilot(request)

        output.mkdir(parents=True)
        (output / "source-reference.json").write_text(
            json.dumps(
                {
                    "commit": manifest["commit"],
                    "archive_sha256": manifest["archive_sha256"],
                },
                indent=2,
            )
            + "\n"
        )
        print("START", args.model, manifest["commit"], flush=True)
        result = b.run_benchmark(config, executors={"repopilot": execute}, preflight_runner=b.preflight_benchmark_image)
        for row in result.results:
            print(
                json.dumps(
                    {
                        "model": args.model,
                        "status": row.status,
                        "repository_pass": row.success,
                        "task_pass": row.evaluation.get("task_pass"),
                        "error": row.error,
                    }
                ),
                flush=True,
            )
        print("DONE", args.model, flush=True)


if __name__ == "__main__":
    main()
