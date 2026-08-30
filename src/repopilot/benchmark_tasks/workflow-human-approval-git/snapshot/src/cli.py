"""Command-line entry point for the status label example."""

from __future__ import annotations

import argparse

from labels import status_label


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("title")
    parser.add_argument("--done", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    print(f"[{status_label(arguments.done)}] {arguments.title}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
