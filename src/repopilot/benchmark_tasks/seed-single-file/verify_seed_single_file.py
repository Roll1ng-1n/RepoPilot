"""Hidden host verifier for the single-file seed task."""

from __future__ import annotations

import sys
from pathlib import Path

sys.dont_write_bytecode = True


def verify(repository: Path) -> None:
    sys.path.insert(0, str(repository / "src"))
    from slugify import slugify

    assert slugify("  RepoPilot \t benchmark  ") == "repopilot-benchmark"
    assert slugify("one  two\nthree") == "one-two-three"
    assert slugify("  [RepoPilot]!  ") == "[repopilot]!"
    assert slugify(" \t\n ") == ""


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
