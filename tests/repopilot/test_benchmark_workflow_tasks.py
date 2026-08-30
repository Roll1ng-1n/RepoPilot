"""Behavioral checks for the workflow and Human Approval/Git benchmark tasks."""

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
TASK_IDS = ("workflow-long-chain", "workflow-human-approval-git")
EXPECTED_RUN_BUDGET = {
    "max_steps": 15,
    "max_replans": 1,
    "max_consecutive_failures": 2,
    "command_timeout_seconds": 30,
    "max_run_seconds": 180,
}
EXPECTED_METADATA = {
    "workflow-long-chain": {
        "revision": "workflow-v1",
        "verifier": "verify_workflow_long_chain.py",
    },
    "workflow-human-approval-git": {
        "revision": "approval-git-v1",
        "verifier": "verify_workflow_human_approval_git.py",
    },
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
    verifier_path = task_directory / str(manifest["verifier"]["path"])  # type: ignore[index]
    return subprocess.run(
        [sys.executable, str(verifier_path), str(repository)],
        capture_output=True,
        text=True,
        check=False,
        env=environment,
        timeout=20,
    )


@pytest.mark.parametrize("task_id", TASK_IDS)
def test_workflow_manifests_and_snapshots_are_stable(task_id: str) -> None:
    task_directory, manifest = _load_manifest(task_id)
    snapshot = task_directory / str(manifest["snapshot"]["path"])  # type: ignore[index]
    snapshot_metadata = manifest["snapshot"]  # type: ignore[assignment]
    expected = EXPECTED_METADATA[task_id]

    assert manifest["schema_version"] == 1
    assert manifest["id"] == task_id
    assert snapshot.is_dir()
    assert snapshot_metadata["revision"] == expected["revision"]
    assert snapshot_metadata["sha256"] == _canonical_snapshot_hash(snapshot)
    assert isinstance(manifest["task_statement"], str) and manifest["task_statement"]
    assert manifest["timeout_seconds"] == 180
    assert manifest["run_budget"] == EXPECTED_RUN_BUDGET
    assert manifest["success_condition"] == {"verifier_exit_code": 0}
    assert manifest["verifier"] == {
        "path": expected["verifier"],
        "execution": "host",
        "timeout_seconds": 20,
    }
    assert not any(path.name.startswith("verify_workflow_") for path in snapshot.rglob("*"))
    assert not (snapshot / expected["verifier"]).exists()


@pytest.mark.parametrize("task_id", TASK_IDS)
def test_initial_workflow_snapshot_fails_its_host_verifier(task_id: str) -> None:
    task_directory, manifest = _load_manifest(task_id)
    snapshot = task_directory / str(manifest["snapshot"]["path"])  # type: ignore[index]

    result = _run_verifier(task_directory, snapshot)

    assert result.returncode != 0


def _initialize_git(repository: Path) -> None:
    subprocess.run(["git", "init", "-q", "--initial-branch=main"], cwd=repository, check=True)
    subprocess.run(["git", "config", "user.name", "Benchmark Test"], cwd=repository, check=True)
    subprocess.run(["git", "config", "user.email", "benchmark-test@example.invalid"], cwd=repository, check=True)
    subprocess.run(["git", "add", "--all"], cwd=repository, check=True)
    subprocess.run(["git", "commit", "-qm", "benchmark snapshot"], cwd=repository, check=True)


def _commit(repository: Path, path: str, message: str) -> None:
    subprocess.run(["git", "add", "--", path], cwd=repository, check=True)
    subprocess.run(["git", "commit", "-qm", message], cwd=repository, check=True)


@pytest.mark.parametrize("task_id", TASK_IDS)
def test_known_gold_fix_passes_host_verifier(task_id: str, tmp_path: Path) -> None:
    task_directory, manifest = _load_manifest(task_id)
    snapshot = task_directory / str(manifest["snapshot"]["path"])  # type: ignore[index]
    repository = tmp_path / task_id
    shutil.copytree(snapshot, repository)

    if task_id == "workflow-long-chain":
        (repository / "src" / "command.py").write_text(
            """\
from workflow import build_report


def execute(title: str, detail: str, *, compact: bool = False) -> str:
    return build_report(title, detail, compact=compact)
""",
            encoding="utf-8",
        )
    else:
        _initialize_git(repository)
        (repository / "src" / "labels.py").write_text(
            """\
def status_label(done: bool) -> str:
    return "done" if done else "todo"
""",
            encoding="utf-8",
        )
        _commit(repository, "src/labels.py", "show completed status")

    result = _run_verifier(task_directory, repository)

    assert result.returncode == 0, result.stderr or result.stdout


def test_git_task_requires_a_commit_after_the_initial_revision(tmp_path: Path) -> None:
    task_directory, manifest = _load_manifest("workflow-human-approval-git")
    snapshot = task_directory / str(manifest["snapshot"]["path"])  # type: ignore[index]
    repository = tmp_path / "workflow-human-approval-git"
    shutil.copytree(snapshot, repository)
    _initialize_git(repository)
    (repository / "src" / "labels.py").write_text(
        """\
def status_label(done: bool) -> str:
    return "done" if done else "todo"
""",
        encoding="utf-8",
    )

    uncommitted = _run_verifier(task_directory, repository)
    assert uncommitted.returncode != 0

    _commit(repository, "src/labels.py", "show completed status")
    committed = _run_verifier(task_directory, repository)
    assert committed.returncode == 0, committed.stderr or committed.stdout
