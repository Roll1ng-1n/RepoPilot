"""Presentation formatting for workflow reports."""

from __future__ import annotations


def format_report(title: str, detail: str, *, compact: bool = False) -> str:
    if compact:
        return f"{title}: {detail}"
    return f"{title}\n{detail}"
