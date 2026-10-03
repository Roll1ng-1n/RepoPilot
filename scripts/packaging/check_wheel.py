"""Verify actual wheel metadata and required source/data before installation."""

from __future__ import annotations

import email
import hashlib
import json
import sys
import zipfile
from pathlib import Path


def main():
    wheel = Path(sys.argv[1])
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        metadata = email.message_from_bytes(archive.read(next(n for n in names if n.endswith("/METADATA"))))
        assert metadata["Name"] == "repopilot-runtime"
        assert metadata["License-Expression"] == "MIT"
        assert all("Roll1ng-1n/RepoPilot" in value for value in metadata.get_all("Project-URL"))
        assert not any("__pycache__" in n or n.endswith(".pyc") or n.endswith("/.env") for n in names)
        assert "repopilot/__init__.py" in names and "minisweagent/__init__.py" in names
        assert any(n.endswith("share/repopilot/UPSTREAM.md") for n in names)
        assert any(n.endswith("share/repopilot/LICENSE.md") for n in names)
        entry_points = archive.read(next(n for n in names if n.endswith("/entry_points.txt"))).decode()
        assert "repopilot = repopilot.cli:app" in entry_points
        tasks = [n for n in names if n.startswith("repopilot/benchmark_tasks/") and n.endswith("/manifest.json")]
        assert len(tasks) == 30
        for manifest in tasks:
            folder = manifest.rsplit("/", 1)[0]
            task = json.loads(archive.read(manifest))
            assert any(n.startswith(folder + "/snapshot/") for n in names)
            assert folder + "/" + task["verifier"]["path"] in names
            if task.get("behavior_verifier"):
                assert folder + "/" + task["behavior_verifier"] in names
        print(
            json.dumps(
                {
                    "wheel": wheel.name,
                    "sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(),
                    "bytes": wheel.stat().st_size,
                    "name": metadata["Name"],
                    "version": metadata["Version"],
                    "files": len(names),
                    "task_manifests": len(tasks),
                    "cache_entries": 0,
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
