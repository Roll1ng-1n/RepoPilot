"""Hidden host verifier for the Replan benchmark task."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


def main(repository: str) -> int:
    root = Path(repository).resolve()
    input_path: Path
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".csv", delete=False) as handle:
        input_path = Path(handle.name)
        handle.write("first,1\nsecond,20\nfirst,3\n")
    try:
        command = [sys.executable, str(root / "src" / "cli.py"), str(input_path), "--json"]
        result = subprocess.run(command, cwd=root, capture_output=True, text=True, check=False, timeout=10)
        assert result.returncode == 0, result.stderr
        lines = result.stdout.splitlines()
        assert len(lines) == 3
        assert all(not line.startswith("[") for line in lines)
        assert [json.loads(line) for line in lines] == [
            {"name": "first", "value": 1},
            {"name": "second", "value": 20},
            {"name": "first", "value": 3},
        ]

        human = subprocess.run(
            [sys.executable, str(root / "src" / "cli.py"), str(input_path)],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
        assert human.returncode == 0, human.stderr
        assert human.stdout == "first: 1\nsecond: 20\nfirst: 3\n"
    finally:
        input_path.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1]))
