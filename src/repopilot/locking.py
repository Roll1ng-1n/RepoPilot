"""Process-owned run lock; kernel releases it after a crash."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path


@contextmanager
def run_lock(directory: Path):
    import fcntl

    # Do not unlink: replacing a locked inode would permit two owners.
    with (directory / "run.lock").open("a+") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ValueError("Agent Run is active in another process.") from error
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)
