"""Hidden host verifier for the long-chain workflow task."""

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


def verify(repository: Path) -> None:
    default = _run(repository, "  Repo   Pilot ", "Ship   safely! ")
    assert default.returncode == 0, default.stderr
    assert default.stdout == "Repo Pilot\nShip safely!\n"

    compact = _run(repository, "  Repo   Pilot ", "Ship   safely! ", "--compact")
    assert compact.returncode == 0, compact.stderr
    assert compact.stdout == "Repo Pilot: Ship safely!\n"

    punctuation = _run(repository, "Release", "Keep: v1.2!", "--compact")
    assert punctuation.returncode == 0, punctuation.stderr
    assert punctuation.stdout == "Release: Keep: v1.2!\n"


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
