"""Checkpoint validation helpers for Target Repository identity and Git state."""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path
from typing import Any


class RepositoryStateError(ValueError):
    """A Target Repository cannot safely be matched to a Checkpoint."""


def capture_repository_state(target_repository: Path) -> dict[str, str]:
    """Describe the exact Git working state required before a Run can resume."""

    target = target_repository.resolve()
    try:
        git_root = _git(target, "rev-parse", "--show-toplevel").decode().strip()
    except RepositoryStateError:
        return _non_git_repository_state(target)
    head = _git(target, "rev-parse", "HEAD").decode().strip()
    status = _git(target, "status", "--porcelain=v1", "--untracked-files=all").decode()
    tracked_diff = _git(target, "diff", "--no-ext-diff", "--binary", "HEAD", "--")
    untracked = _git(target, "ls-files", "--others", "--exclude-standard", "-z")
    fingerprint_source = bytearray()
    fingerprint_source.extend(head.encode())
    fingerprint_source.extend(b"\0")
    fingerprint_source.extend(status.encode())
    fingerprint_source.extend(b"\0")
    fingerprint_source.extend(tracked_diff)
    for relative_path in untracked.split(b"\0"):
        if not relative_path:
            continue
        path = Path(git_root) / relative_path.decode(errors="surrogateescape")
        try:
            contents = path.read_bytes()
        except OSError as error:
            raise RepositoryStateError(f"Could not read untracked file {path}: {error}") from error
        fingerprint_source.extend(b"\0")
        fingerprint_source.extend(relative_path)
        fingerprint_source.extend(b"\0")
        fingerprint_source.extend(contents)
    return {
        "resolved_target_repository": str(target),
        "git_root": str(Path(git_root).resolve()),
        "head": head,
        "status": status,
        "diff_fingerprint": hashlib.sha256(fingerprint_source).hexdigest(),
    }


def _non_git_repository_state(target_repository: Path) -> dict[str, str]:
    """Keep runtime-only callers working while making a non-Git state auditable."""

    fingerprint_source = bytearray()
    for path in sorted(target_repository.rglob("*")):
        if not path.is_file():
            continue
        relative_path = path.relative_to(target_repository)
        fingerprint_source.extend(str(relative_path).encode())
        fingerprint_source.extend(b"\0")
        fingerprint_source.extend(path.read_bytes())
        fingerprint_source.extend(b"\0")
    return {
        "resolved_target_repository": str(target_repository),
        "git_root": "",
        "head": "",
        "status": "",
        "diff_fingerprint": hashlib.sha256(fingerprint_source).hexdigest(),
    }


def verify_repository_state(expected: dict[str, Any], target_repository: Path) -> dict[str, str]:
    """Reject a resume when its Target Repository differs from its Checkpoint."""

    actual = capture_repository_state(target_repository)
    fields = ("resolved_target_repository", "git_root", "head", "status", "diff_fingerprint")
    mismatches = [field for field in fields if expected.get(field) != actual[field]]
    if mismatches:
        raise RepositoryStateError("Target Repository changed since the Checkpoint: " + ", ".join(mismatches) + ".")
    return actual


def _git(target_repository: Path, *arguments: str) -> bytes:
    try:
        completed = subprocess.run(
            ("git", "-C", str(target_repository), *arguments),
            capture_output=True,
            check=False,
        )
    except OSError as error:
        raise RepositoryStateError(f"Could not inspect Target Repository: {error}") from error
    if completed.returncode != 0:
        detail = completed.stderr.decode(errors="replace").strip()
        raise RepositoryStateError(detail or "Target Repository is not a Git repository.")
    return completed.stdout
