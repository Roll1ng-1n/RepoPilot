"""Rendering helpers used by the Replan benchmark task."""

from __future__ import annotations

from collections.abc import Iterable


def render_report(rows: Iterable[tuple[str, int]]) -> str:
    """Render rows in the existing human-readable format."""

    return "\n".join(f"{name}: {value}" for name, value in rows)
