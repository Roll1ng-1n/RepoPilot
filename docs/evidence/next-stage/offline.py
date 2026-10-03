"""Validate pinned task hashes and known repairs without credentials or model calls."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from repopilot.benchmark import load_tasks

HERE = Path(__file__).resolve().parent


def main():
    rows = []
    for task in load_tasks(HERE / "tasks"):
        if not task.task_id.startswith("real-"):
            rows.append({"task_id": task.task_id, "snapshot_sha256": task.snapshot_sha256, "hash_valid": True})
            continue
        with tempfile.TemporaryDirectory(prefix="repopilot-offline-") as temporary:
            workspace = Path(temporary) / "workspace"
            shutil.copytree(task.snapshot, workspace)
            command = [sys.executable, "-B", "-m", "unittest", "discover", "-s", "checks"]
            before = subprocess.run(command, cwd=workspace, capture_output=True, text=True)
            patch = task.manifest_path.parent / "solution.diff"
            subprocess.run(["git", "apply", str(patch)], cwd=workspace, check=True)
            after = subprocess.run(command, cwd=workspace, capture_output=True, text=True)
            verifier = subprocess.run(
                [sys.executable, "-B", str(task.verifier_path), str(workspace)], capture_output=True, text=True
            )
            rows.append(
                {
                    "task_id": task.task_id,
                    "snapshot_sha256": task.snapshot_sha256,
                    "hash_valid": True,
                    "before_exit_code": before.returncode,
                    "after_exit_code": after.returncode,
                    "verifier_exit_code": verifier.returncode,
                    "before_output": before.stderr,
                    "after_output": after.stderr,
                    "verifier_output": verifier.stderr,
                }
            )
            if not (before.returncode != 0 and after.returncode == 0 and verifier.returncode == 0):
                raise RuntimeError(rows[-1])
    (HERE / "offline-results.json").write_text(json.dumps(rows, indent=2) + "\n")
    print(f"Validated {len(rows)} task snapshots; all seeded failures and known repairs verified.")


if __name__ == "__main__":
    main()
