from __future__ import annotations

import argparse

from greetings import format_greeting


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("name")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    print(format_greeting(args.name))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
