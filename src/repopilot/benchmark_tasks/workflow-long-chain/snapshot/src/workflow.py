"""Application workflow for building a normalized report."""

from __future__ import annotations

from formatting import format_report


def build_report(title: str, detail: str, *, compact: bool = False) -> str:
    clean_title = " ".join(title.split())
    clean_detail = " ".join(detail.split())
    return format_report(clean_title, clean_detail, compact=compact)
