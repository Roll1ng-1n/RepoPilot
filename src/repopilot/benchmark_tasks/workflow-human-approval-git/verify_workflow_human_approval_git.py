"""Hidden host verifier for the Human Approval/Git task."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True


def _run(repository: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-B", str(repository / "src" / "cli.py"), *arguments],
        cwd=repository,
        capture_output=True,
        text=True,
        check=False,
        timeout=5,
    )


def _git(repository: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *arguments],
        cwd=repository,
        capture_output=True,
        text=True,
        check=False,
        timeout=5,
    )


def verify(repository: Path) -> None:
    default = _run(repository, "Ship parser")
    assert default.returncode == 0, default.stderr
    assert default.stdout == "[todo] Ship parser\n"

    done = _run(repository, "Ship parser", "--done")
    assert done.returncode == 0, done.stderr
    assert done.stdout == "[done] Ship parser\n"

    top_level = _git(repository, "rev-parse", "--show-toplevel")
    assert top_level.returncode == 0, top_level.stderr
    assert Path(top_level.stdout.strip()).resolve() == repository.resolve()

    initial = _git(repository, "rev-list", "--max-parents=0", "HEAD")
    assert initial.returncode == 0, initial.stderr
    roots = [line for line in initial.stdout.splitlines() if line]
    assert len(roots) == 1

    followup = _git(repository, "rev-list", "--count", f"{roots[0]}..HEAD")
    assert followup.returncode == 0, followup.stderr
    assert int(followup.stdout.strip()) >= 1

    changed_files = _git(repository, "diff", "--name-only", f"{roots[0]}..HEAD")
    assert changed_files.returncode == 0, changed_files.stderr
    assert "src/labels.py" in changed_files.stdout.splitlines()


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    if len(arguments) != 1:
        print("usage: verifier.py REPOSITORY", file=sys.stderr)
        return 2
    try:
        verify(Path(arguments[0]).resolve())
    except Exception as error:
        print(f"hidden verification failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
