from __future__ import annotations

import argparse
from pathlib import Path

from report import render_report


def _read_rows(path: Path) -> list[tuple[str, int]]:
    return [
        (name, int(value))
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
        for name, value in [line.split(",", 1)]
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input")
    args = parser.parse_args(argv)
    print(render_report(_read_rows(Path(args.input))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
