"""Freeze evaluation source and inputs before any paid call."""

from __future__ import annotations

import hashlib
import json
import subprocess
import tarfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
archive = HERE / "source.tar.gz"
if archive.exists():
    raise SystemExit("Refusing to overwrite frozen source.")
files = sorted(p for p in (ROOT / "src").rglob("*") if p.is_file() and "__pycache__" not in p.parts)
with tarfile.open(archive, "w:gz") as tar:
    for path in files:
        tar.add(path, arcname=str(path.relative_to(ROOT)))
manifest = {
    "base_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
    "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
    "files": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
    "experiment_files": {
        str(p.relative_to(HERE)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(HERE.rglob("*"))
        if p.is_file()
        and "__pycache__" not in p.parts
        and (p.is_relative_to(HERE / "tasks") or p.name in {"evaluation-plan.json", "run_models.py", "offline.py"})
    },
}
(HERE / "source-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
print(manifest["archive_sha256"])
