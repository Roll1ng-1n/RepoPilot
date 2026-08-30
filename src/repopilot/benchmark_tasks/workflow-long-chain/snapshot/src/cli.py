"""Command-line entry point for the report workflow."""

from __future__ import annotations

import argparse

from command import execute


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("title")
    parser.add_argument("detail")
    parser.add_argument("--compact", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    print(execute(arguments.title, arguments.detail, compact=arguments.compact))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
