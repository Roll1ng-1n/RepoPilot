"""Objective negative/positive controls for every fixed Stage 4 task.

Solutions remain on the host, outside snapshots. These are verifier checks,
not model success claims or evidence of behavioral capability.
"""

import json
import shlex
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pytest

from repopilot.benchmark import canonical_snapshot_sha256

TASKS = Path(__file__).resolve().parents[2] / "src/repopilot/benchmark_tasks"
MANIFESTS = sorted(TASKS.glob("*/manifest.json"))


def _git(repository: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repository, check=True, capture_output=True, text=True)


def test_fixed_category_coverage():
    manifests = [json.loads(path.read_text()) for path in MANIFESTS]
    assert len(manifests) == 30
    assert Counter(item["category"] for item in manifests) == {
        category: 5 for category in ["simple", "cross-file", "recovery", "replan", "long-horizon", "hitl"]
    }
    for manifest in manifests:
        assert isinstance(manifest["capabilities"], list)
        assert isinstance(manifest["behavior_requirements"], list)


@pytest.mark.parametrize("path", MANIFESTS, ids=lambda path: path.parent.name)
def test_snapshot_fails_and_host_solution_passes(path, tmp_path):
    manifest = json.loads(path.read_text())
    snapshot = path.parent / manifest["snapshot"]["path"]
    assert canonical_snapshot_sha256(snapshot) == manifest["snapshot"]["sha256"]
    repository = tmp_path / "repository"
    shutil.copytree(snapshot, repository)
    assert not (repository / "solution.json").exists()
    _git(repository, "init")
    _git(repository, "config", "user.name", "Verifier Fixture")
    _git(repository, "config", "user.email", "fixture@example.invalid")
    _git(repository, "add", ".")
    _git(repository, "commit", "-m", "initial snapshot")
    command = [sys.executable, "-B", str(path.parent / manifest["verifier"]["path"]), str(repository)]
    compile((path.parent / manifest["verifier"]["path"]).read_text(), str(path), "exec")
    initial = subprocess.run(command, capture_output=True, text=True, timeout=20)
    assert initial.returncode != 0, "broken snapshot unexpectedly passes"
    public_command = None
    if manifest["category"] == "recovery":
        public_command = [sys.executable, "-B", *shlex.split(manifest["behavior_spec"]["recovery_command"])[1:]]
        public_initial = subprocess.run(public_command, cwd=repository, capture_output=True, text=True, timeout=20)
        assert public_initial.returncode != 0, "required recoverable failure does not occur"
    for relative, content in json.loads((path.parent / "solution.json").read_text()).items():
        (repository / relative).write_text(content)
    if manifest["category"] == "hitl" and manifest.get("approval_policy", "approve") == "approve":
        if (path.parent / "verify.py").exists():
            _git(repository, "commit", "--allow-empty", "-m", "unrelated commit")
            unrelated = subprocess.run(command, capture_output=True, text=True, timeout=20)
            assert unrelated.returncode != 0, "unrelated commit must not satisfy committing the source fix"
        _git(repository, "add", ".")
        _git(repository, "commit", "-m", "apply verified fix")
    solved = subprocess.run(command, capture_output=True, text=True, timeout=20)
    assert solved.returncode == 0, solved.stderr
    if public_command:
        public_solved = subprocess.run(public_command, cwd=repository, capture_output=True, text=True, timeout=20)
        assert public_solved.returncode == 0, public_solved.stderr
    # A partial fix that leaves any required source change undone must fail.
    # Each verifier invocation is a fresh process: shared module names such as
    # feature/pipeline cannot leak between tasks or from positive to negative runs.
    for relative, content in json.loads((path.parent / "solution.json").read_text()).items():
        (repository / relative).write_bytes((snapshot / relative).read_bytes())
        partial = subprocess.run(command, capture_output=True, text=True, timeout=20)
        assert partial.returncode != 0, f"verifier accepted incomplete fix: {relative}"
        (repository / relative).write_text(content)
    if manifest.get("approval_policy") == "reject":
        _git(repository, "add", ".")
        _git(repository, "commit", "--amend", "-m", "incorrectly amend after rejection")
        amended = subprocess.run(command, capture_output=True, text=True, timeout=20)
        assert amended.returncode != 0, "amending the root commit must not bypass the no-commit condition"


def test_recovery_verifier_rejects_public_sample_lookup(tmp_path):
    task = TASKS / "recovery-import-path"
    repository = tmp_path / "repository"
    shutil.copytree(task / "snapshot", repository)
    (repository / "src/loader.py").write_text(
        "def load(text):\n    return {' 3, -1, 5 ': [3, -1, 5], '0': [0]}.get(text, [])\n"
    )
    public = subprocess.run(
        [sys.executable, "-B", "public_test.py"], cwd=repository, capture_output=True, text=True, timeout=20
    )
    assert public.returncode == 0, public.stderr
    hidden = subprocess.run(
        [sys.executable, "-B", str(task / "verify.py"), str(repository)],
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert hidden.returncode != 0
