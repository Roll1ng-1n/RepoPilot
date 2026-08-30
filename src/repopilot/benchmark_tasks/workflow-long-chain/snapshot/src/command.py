"""Command adapter for the report workflow."""

from __future__ import annotations

from workflow import build_report


def execute(title: str, detail: str, *, compact: bool = False) -> str:
    return build_report(title, detail)
