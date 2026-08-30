"""Regression checks for the benchmark's Recovery and Replan task snapshots."""

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
TASK_IDS = ("recovery-public-failure", "replan-new-evidence")
EXPECTED_REVISIONS = {
    "recovery-public-failure": "recovery-v1",
    "replan-new-evidence": "replan-v1",
}
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
    return task_directory, json.loads(manifest_path.read_text(encoding="utf-8"))


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
    manifest = json.loads((task_directory / "manifest.json").read_text(encoding="utf-8"))
    verifier_path = task_directory / manifest["verifier"]["path"]
    return subprocess.run(
        [sys.executable, str(verifier_path), str(repository)],
        capture_output=True,
        text=True,
        check=False,
        env=environment,
        timeout=20,
    )


def _run_public_tests(repository: Path) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests"],
        cwd=repository,
        capture_output=True,
        text=True,
        check=False,
        env=environment,
        timeout=20,
    )


@pytest.mark.parametrize("task_id", TASK_IDS)
def test_manifest_and_snapshot_are_fixed_and_verifier_is_host_only(task_id: str) -> None:
    task_directory, manifest = _load_manifest(task_id)
    snapshot = task_directory / str(manifest["snapshot"]["path"])  # type: ignore[index]
    snapshot_metadata = manifest["snapshot"]  # type: ignore[assignment]

    assert manifest["schema_version"] == 1
    assert manifest["id"] == task_id
    assert snapshot.is_dir()
    assert snapshot_metadata["revision"] == EXPECTED_REVISIONS[task_id]  # type: ignore[index]
    assert snapshot_metadata["sha256"] == _canonical_snapshot_hash(snapshot)  # type: ignore[index]
    assert isinstance(manifest["task_statement"], str) and manifest["task_statement"]
    assert manifest["timeout_seconds"] == 180
    assert manifest["run_budget"] == EXPECTED_RUN_BUDGET
    assert manifest["success_condition"] == {"verifier_exit_code": 0}
    assert manifest["verifier"] == {
        "path": f"verify_{task_id.replace('-', '_')}.py",
        "execution": "host",
        "timeout_seconds": 20,
    }
    assert not any(path.name.startswith("verify_") for path in snapshot.rglob("*"))
    assert not (snapshot / str(manifest["verifier"]["path"])).exists()  # type: ignore[index]


@pytest.mark.parametrize("task_id", TASK_IDS)
def test_initial_snapshot_fails_hidden_verifier(task_id: str) -> None:
    task_directory, manifest = _load_manifest(task_id)
    snapshot = task_directory / str(manifest["snapshot"]["path"])  # type: ignore[index]

    result = _run_verifier(task_directory, snapshot)

    assert result.returncode != 0


def test_recovery_shallow_casefold_fix_fails_public_tests(tmp_path: Path) -> None:
    task_directory, manifest = _load_manifest("recovery-public-failure")
    snapshot = task_directory / str(manifest["snapshot"]["path"])  # type: ignore[index]
    repository = tmp_path / "recovery-public-failure"
    shutil.copytree(snapshot, repository)

    (repository / "src" / "line_tools.py").write_text(
        """\
from collections.abc import Iterable


def unique_clean_lines(lines: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for line in lines:
        value = line.strip().casefold()
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result
""",
        encoding="utf-8",
    )

    public_result = _run_public_tests(repository)
    hidden_result = _run_verifier(task_directory, repository)

    assert public_result.returncode != 0
    assert hidden_result.returncode != 0


def test_recovery_corrected_fix_passes_hidden_verifier(tmp_path: Path) -> None:
    task_directory, manifest = _load_manifest("recovery-public-failure")
    snapshot = task_directory / str(manifest["snapshot"]["path"])  # type: ignore[index]
    repository = tmp_path / "recovery-public-failure"
    shutil.copytree(snapshot, repository)

    (repository / "src" / "line_tools.py").write_text(
        """\
from collections.abc import Iterable


def unique_clean_lines(lines: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for line in lines:
        value = line.strip()
        key = value.casefold()
        if value and key not in seen:
            seen.add(key)
            result.append(value)
    return result
""",
        encoding="utf-8",
    )

    result = _run_verifier(task_directory, repository)

    assert result.returncode == 0, result.stderr or result.stdout


def test_replan_initial_json_array_plan_is_rejected_by_public_contract(tmp_path: Path) -> None:
    task_directory, manifest = _load_manifest("replan-new-evidence")
    snapshot = task_directory / str(manifest["snapshot"]["path"])  # type: ignore[index]
    repository = tmp_path / "replan-new-evidence"
    shutil.copytree(snapshot, repository)

    (repository / "src" / "report.py").write_text(
        """\
from __future__ import annotations

import json
from collections.abc import Iterable


def render_report(rows: Iterable[tuple[str, int]], *, machine: bool = False) -> str:
    values = [{"name": name, "value": value} for name, value in rows]
    if machine:
        return json.dumps(values, separators=(",", ":"))
    return "\\n".join(f"{item['name']}: {item['value']}" for item in values)
""",
        encoding="utf-8",
    )
    (repository / "src" / "cli.py").write_text(
        """\
from __future__ import annotations

import argparse
from pathlib import Path

from report import render_report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    rows = [
        (name, int(value))
        for line in Path(args.input).read_text(encoding="utf-8").splitlines()
        if line.strip()
        for name, value in [line.split(",", 1)]
    ]
    print(render_report(rows, machine=args.json))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
""",
        encoding="utf-8",
    )

    public_result = _run_public_tests(repository)
    hidden_result = _run_verifier(task_directory, repository)

    assert public_result.returncode != 0
    assert hidden_result.returncode != 0


def test_replan_ndjson_plan_passes_hidden_verifier(tmp_path: Path) -> None:
    task_directory, manifest = _load_manifest("replan-new-evidence")
    snapshot = task_directory / str(manifest["snapshot"]["path"])  # type: ignore[index]
    repository = tmp_path / "replan-new-evidence"
    shutil.copytree(snapshot, repository)

    (repository / "src" / "report.py").write_text(
        """\
from __future__ import annotations

import json
from collections.abc import Iterable


def render_report(rows: Iterable[tuple[str, int]], *, machine: bool = False) -> str:
    values = [{"name": name, "value": value} for name, value in rows]
    if machine:
        return "\\n".join(json.dumps(item, separators=(",", ":")) for item in values)
    return "\\n".join(f"{item['name']}: {item['value']}" for item in values)
""",
        encoding="utf-8",
    )
    (repository / "src" / "cli.py").write_text(
        """\
from __future__ import annotations

import argparse
from pathlib import Path

from report import render_report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    rows = [
        (name, int(value))
        for line in Path(args.input).read_text(encoding="utf-8").splitlines()
        if line.strip()
        for name, value in [line.split(",", 1)]
    ]
    print(render_report(rows, machine=args.json))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
""",
        encoding="utf-8",
    )

    result = _run_verifier(task_directory, repository)

    assert result.returncode == 0, result.stderr or result.stdout
