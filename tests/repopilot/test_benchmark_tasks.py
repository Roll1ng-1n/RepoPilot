"""Deterministic checks for the fixed Agent Benchmark seed tasks."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
TASKS_ROOT = REPOSITORY_ROOT / "src" / "repopilot" / "benchmark_tasks"
TASK_IDS = ("seed-single-file", "seed-cross-file")
EXPECTED_RUN_BUDGET = {
    "max_steps": 15,
    "max_replans": 1,
    "max_consecutive_failures": 2,
    "command_timeout_seconds": 30,
    "max_run_seconds": 180,
}


def _load_manifest(task_id: str) -> tuple[Path, dict[str, object]]:
    task_directory = TASKS_ROOT / task_id
    manifest_path = task_directory / "manifest.json"
    return task_directory, json.loads(manifest_path.read_text())


def _canonical_snapshot_hash(snapshot: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(path for path in snapshot.rglob("*") if path.is_file()):
        relative_path = path.relative_to(snapshot).as_posix()
        digest.update(relative_path.encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _run_verifier(task_directory: Path, repository: Path) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    manifest = json.loads((task_directory / "manifest.json").read_text())
    verifier_path = task_directory / manifest["verifier"]["path"]
    return subprocess.run(
        [sys.executable, str(verifier_path), str(repository)],
        capture_output=True,
        text=True,
        check=False,
        env=environment,
        timeout=20,
    )


@pytest.mark.parametrize("task_id", TASK_IDS)
def test_seed_manifest_and_snapshot_are_stable(task_id: str) -> None:
    task_directory, manifest = _load_manifest(task_id)
    snapshot = task_directory / str(manifest["snapshot"]["path"])  # type: ignore[index]
    snapshot_metadata = manifest["snapshot"]  # type: ignore[assignment]

    assert manifest["schema_version"] == 1
    assert manifest["id"] == task_id
    assert snapshot.is_dir()
    assert snapshot_metadata["revision"] == "seed-v1"
    assert snapshot_metadata["sha256"] == _canonical_snapshot_hash(snapshot)
    assert isinstance(manifest["task_statement"], str) and manifest["task_statement"]
    assert manifest["timeout_seconds"] == 180
    assert manifest["run_budget"] == EXPECTED_RUN_BUDGET
    assert manifest["success_condition"] == {"verifier_exit_code": 0}
    assert manifest["verifier"] == {
        "path": f"verify_{task_id.replace('-', '_')}.py",
        "execution": "host",
        "timeout_seconds": 20,
    }
    assert not any(path.name.startswith("verify_seed_") for path in snapshot.rglob("*"))
    assert not (snapshot / str(manifest["verifier"]["path"])).exists()  # type: ignore[index]


@pytest.mark.parametrize("task_id", TASK_IDS)
def test_initial_snapshot_fails_its_host_verifier(task_id: str) -> None:
    task_directory, manifest = _load_manifest(task_id)
    snapshot = task_directory / str(manifest["snapshot"]["path"])  # type: ignore[index]

    result = _run_verifier(task_directory, snapshot)

    assert result.returncode != 0


@pytest.mark.parametrize("task_id", TASK_IDS)
def test_known_gold_fix_passes_host_verifier_without_mounting_verifier(task_id: str, tmp_path: Path) -> None:
    task_directory, manifest = _load_manifest(task_id)
    snapshot = task_directory / str(manifest["snapshot"]["path"])  # type: ignore[index]
    repository = tmp_path / task_id
    shutil.copytree(snapshot, repository)

    if task_id == "seed-single-file":
        (repository / "src" / "slugify.py").write_text(
            """\
def slugify(value: str) -> str:
    return "-".join(value.lower().split())
"""
        )
    else:
        (repository / "src" / "greetings.py").write_text(
            """\
def format_greeting(name: str, excited: bool = False) -> str:
    if excited:
        return f"HELLO, {name.upper()}!"
    return f"Hello, {name}"
"""
        )
        (repository / "src" / "cli.py").write_text(
            """\
from __future__ import annotations

import argparse

from greetings import format_greeting


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("name")
    parser.add_argument("--excited", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    print(format_greeting(args.name, excited=args.excited))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
"""
        )

    result = _run_verifier(task_directory, repository)

    assert result.returncode == 0, result.stderr or result.stdout
