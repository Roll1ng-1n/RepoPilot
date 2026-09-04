"""Hidden host verifier for the Recovery benchmark task."""

from __future__ import annotations

import sys
from pathlib import Path

sys.dont_write_bytecode = True


def main(repository: str) -> int:
    root = Path(repository).resolve()
    sys.path.insert(0, str(root))
    from src.line_tools import unique_clean_lines

    values = (value for value in ["  Straße ", "STRASSE", "", " beta", "Beta ", "  "])
    assert unique_clean_lines(values) == ["Straße", "beta"]
    assert unique_clean_lines(["A", "a", " A ", "B"]) == ["A", "B"]
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1]))
