"""Capture raw worktree content without changing the index or invoking clean filters."""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

from repopilot.checkpoint import capture_repository_state


def snapshot(repository: Path):
    state = capture_repository_state(repository)
    if not state["git_root"]:
        return {"state": state, "tree": None}
    root = Path(state["git_root"])
    with tempfile.TemporaryDirectory(prefix="repopilot-index-") as temporary:
        env = {**os.environ, "GIT_INDEX_FILE": str(Path(temporary) / "index")}

        def git(*args, data=None):
            return subprocess.run(
                ["git", "-C", str(root), *args], env=env, input=data, capture_output=True, check=True, timeout=30
            ).stdout

        names = sorted(
            set(
                subprocess.run(
                    ["git", "-C", str(root), "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
                    capture_output=True,
                    check=True,
                    timeout=30,
                ).stdout.split(b"\0")
            )
            - {b""}
        )
        entries = []
        regular = []
        for name in names:
            path = root / os.fsdecode(name)
            if path.is_symlink():
                oid = git("hash-object", "-w", "--stdin", data=os.fsencode(os.readlink(path))).strip()
                entries.append(b"120000 " + oid + b"\t" + name + b"\0")
            elif path.is_file():
                regular.append(name)
            elif path.is_dir():
                # Keep a submodule's currently checked-out commit; do not recurse or run filters.
                oid = subprocess.run(
                    ["git", "-C", str(path), "rev-parse", "HEAD"], capture_output=True, check=True, timeout=30
                ).stdout.strip()
                entries.append(b"160000 " + oid + b"\t" + name + b"\0")
        for offset in range(0, len(regular), 100):
            batch = regular[offset : offset + 100]
            oids = git("hash-object", "-w", "--no-filters", "--", *(os.fsdecode(n) for n in batch)).splitlines()
            for name, oid in zip(batch, oids, strict=True):
                mode = b"100755" if (root / os.fsdecode(name)).stat().st_mode & 0o111 else b"100644"
                entries.append(mode + b" " + oid + b"\t" + name + b"\0")
        git("read-tree", "--empty")
        git("update-index", "-z", "--index-info", data=b"".join(entries))
        tree = git("write-tree").decode().strip()
    return {"state": state, "tree": tree}


def diff(repository: Path, before: str, after: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repository), "diff", "--no-ext-diff", "--binary", "--full-index", before, after, "--"],
        capture_output=True,
        check=True,
        timeout=30,
    ).stdout.decode(errors="surrogateescape")
