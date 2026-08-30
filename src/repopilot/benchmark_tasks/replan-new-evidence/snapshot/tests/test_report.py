# ruff: noqa: PT009

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "tests" / "items.csv"


class ReportOutputTests(unittest.TestCase):
    def test_json_mode_follows_the_documented_ndjson_protocol(self) -> None:
        result = subprocess.run(
            [sys.executable, str(ROOT / "src" / "cli.py"), str(INPUT), "--json"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            result.stdout,
            '{"name":"alpha","value":2}\n{"name":"Beta","value":3}\n',
        )
        self.assertEqual(
            [json.loads(line) for line in result.stdout.splitlines()],
            [
                {"name": "alpha", "value": 2},
                {"name": "Beta", "value": 3},
            ],
        )

    def test_human_mode_remains_unchanged(self) -> None:
        result = subprocess.run(
            [sys.executable, str(ROOT / "src" / "cli.py"), str(INPUT)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "alpha: 2\nBeta: 3\n")


if __name__ == "__main__":
    unittest.main()
