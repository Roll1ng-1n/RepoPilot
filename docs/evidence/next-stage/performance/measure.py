"""Development checkpoint benchmark; five repetitions, no models or CI time limits."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import resource
import statistics
import subprocess
import tempfile
import time
import types
from pathlib import Path

from repopilot.artifacts import RunArtifacts
from repopilot.checkpoint import capture_repository_state

HERE = Path(__file__).resolve().parent


def percentile(values, probability):
    values = sorted(values)
    position = (len(values) - 1) * probability
    lower = int(position)
    return values[lower] + (values[min(lower + 1, len(values) - 1)] - values[lower]) * (position - lower)


def measure(mode, *, cold=False):
    artifact_class = RunArtifacts
    baseline_source = HERE.parent / "checkpoint-baseline.py.txt"
    if mode == "baseline":
        module = types.ModuleType("checkpoint_baseline")
        exec(compile(baseline_source.read_text(), str(baseline_source), "exec"), module.__dict__)
        artifact_class = module.RunArtifacts
    rows = []
    with tempfile.TemporaryDirectory(prefix="repopilot-checkpoint-perf-") as temporary:
        root = Path(temporary)
        repository = root / "repository"
        repository.mkdir()
        for number in range(10000):
            (repository / f"file-{number:05d}.py").write_text(f"value = {number}\n")
        for command in (
            ["git", "init", "-q"],
            ["git", "add", "."],
            [
                "git",
                "-c",
                "user.name=Fixture",
                "-c",
                "user.email=fixture@example.invalid",
                "commit",
                "-qm",
                "10k visible sources",
            ],
        ):
            subprocess.run(command, cwd=repository, check=True)
        fixture_sha = hashlib.sha256(
            b"10k file-{i:05d}.py: value = {i}\\n; outputs unique by i, deterministic x padding; messages carry receipt, complete tool_results carry stdout; five independent complete saves per fixed history"
        ).hexdigest()
        for size in (100 * 1024, 1024 * 1024):
            for count in (100, 500, 1000):
                payloads = [
                    f"result-{i:04d}:fixture-secret-token:" + "x" * (size - 60) + f":end-{i:04d}" for i in range(count)
                ]
                checkpoint = {
                    "schema_version": 2,
                    "run_id": "fixture",
                    "status": "RUNNING",
                    "task": "measure persistence",
                    "messages": [
                        {
                            "role": "tool",
                            "tool_call_id": str(i),
                            "content": f"Output stored for call {i}; continue via artifact.",
                        }
                        for i in range(count)
                    ],
                    "tool_results": [
                        {
                            "tool_call_id": str(i),
                            "tool_name": "read_file",
                            "arguments": {"path": f"file-{i:05d}.py"},
                            "observation": {"ok": True, "result": {"stdout": payload, "exit_code": 0}},
                        }
                        for i, payload in enumerate(payloads)
                    ],
                    "budget": {"steps_used": count},
                    "plan_history": [],
                    "failures": [],
                    "recoveries": [],
                }
                samples = []
                with tempfile.TemporaryDirectory(dir=root, prefix="save-") as run_temp:
                    artifacts = None
                    for repeat in range(5):
                        if artifacts is None or cold:
                            artifacts = artifact_class(Path(run_temp), secrets=["fixture-secret-token"])
                            artifacts.run_id = "fixture"
                        trace_start = len(artifacts.read_trace())
                        objects_before = sum(
                            p.stat().st_size for p in (artifacts.path / "objects").rglob("*") if p.is_file()
                        )
                        trace_bytes_before = (
                            (artifacts.path / "trace.jsonl").stat().st_size
                            if (artifacts.path / "trace.jsonl").exists()
                            else 0
                        )
                        started = time.monotonic()
                        scan_started = time.monotonic()
                        checkpoint["repository"] = capture_repository_state(repository)
                        scan_seconds = time.monotonic() - scan_started
                        artifacts.write_checkpoint(checkpoint)
                        elapsed = time.monotonic() - started
                        trace = artifacts.read_trace()[trace_start:]
                        operations = {
                            name: sum(
                                e.get("duration_seconds", 0)
                                for e in trace
                                if e.get("type") == "operation_finished" and e.get("operation") == name
                            )
                            for name in ("checkpoint_serialization", "checkpoint_write_sync", "checkpoint_objects")
                        }
                        samples.append(
                            {
                                "repeat": repeat + 1,
                                "save_seconds": elapsed,
                                "scan_seconds": scan_seconds,
                                "checkpoint_bytes": (artifacts.path / "checkpoint.json").stat().st_size,
                                "written_bytes": (artifacts.path / "checkpoint.json").stat().st_size
                                + sum(p.stat().st_size for p in (artifacts.path / "objects").rglob("*") if p.is_file())
                                - objects_before
                                + (artifacts.path / "trace.jsonl").stat().st_size
                                - trace_bytes_before,
                                **operations,
                            }
                        )
                numeric = {
                    key: {
                        "median": statistics.median([s[key] for s in samples]),
                        "p95": percentile([s[key] for s in samples], 0.95),
                    }
                    for key in samples[0]
                    if key != "repeat"
                }
                row = {
                    "history_results": count,
                    "output_bytes_target": size,
                    "samples": samples,
                    "summary": numeric,
                    "total_written_bytes": sum(s["written_bytes"] for s in samples),
                }
                rows.append(row)
                print(
                    mode,
                    count,
                    size,
                    round(numeric["save_seconds"]["median"], 3),
                    row["total_written_bytes"],
                    flush=True,
                )
    return {
        "implementation_sha256": {
            str(p): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in [Path(__file__), Path("src/repopilot/artifacts.py"), Path("src/repopilot/checkpoint_storage.py")]
        },
        "mode": mode,
        "cold": cold,
        "machine": {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "filesystem_device": str(subprocess.check_output(["df", "-T", str(HERE)], text=True).splitlines()[-1]),
            "max_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        },
        "fixture_sha256": fixture_sha,
        "baseline_source_sha256": hashlib.sha256(baseline_source.read_bytes()).hexdigest(),
        "repetitions": 5,
        "scope": "Five independent cold complete saves"
        if cold
        else "Five durability-boundary saves of the same immutable history per size, first cold then four warm. All unique text objects, rewritten checkpoints and appended traces counted as actual written bytes. No extrapolation to every tool boundary.",
        "rows": rows,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["baseline", "optimized"], required=True)
    parser.add_argument("--cold", action="store_true")
    args = parser.parse_args()
    result = measure(args.mode, cold=args.cold)
    (HERE / (args.mode + ("-cold" if args.cold else "") + ".json")).write_text(json.dumps(result, indent=2) + "\n")
