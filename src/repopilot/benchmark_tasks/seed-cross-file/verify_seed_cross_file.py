"""Hidden host verifier for the cross-file seed task."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True


def verify(repository: Path) -> None:
    sys.path.insert(0, str(repository / "src"))
    from greetings import format_greeting

    assert format_greeting("Ada") == "Hello, Ada"
    assert format_greeting("Ada", excited=True) == "HELLO, ADA!"  # type: ignore[call-arg]

    result = subprocess.run(
        [sys.executable, "-B", str(repository / "src" / "cli.py"), "Ada", "--excited"],
        cwd=repository,
        capture_output=True,
        text=True,
        check=False,
        timeout=5,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == "HELLO, ADA!\n"

    default_result = subprocess.run(
        [sys.executable, "-B", str(repository / "src" / "cli.py"), "Ada"],
        cwd=repository,
        capture_output=True,
        text=True,
        check=False,
        timeout=5,
    )
    assert default_result.returncode == 0, default_result.stderr
    assert default_result.stdout == "Hello, Ada\n"


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
