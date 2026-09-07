"""Offline evidence recomputation for RepoPilot Stage 4 evaluation.

Reads the full campaign summaries written by ``repopilot campaign`` (raw state
under ``~/.local/state/repopilot/campaigns/<run-id>/summary.json``), merges
their row-level results with a deterministic overlay order, and recomputes the
complete ``evaluation_summary`` (category / capability / numeric / paired)
using the same ``evaluation.aggregate`` / ``evaluation.markdown`` used by the
runner.

Why this exists: ``docs/evidence/*/summary.json`` keeps a curated, redacted
subset of each run. It intentionally does not carry every per-row ``metrics``
and ``evaluation`` object. Raw state does. This module closes the loop so any
conclusion in the evidence docs can be recomputed from raw artifacts, including
environmental-error reruns that replaced rows in the published evidence.

Overlay semantics: campaign files are consumed in argv order. Each row is keyed
by ``(model, round, task_id, engine)``; a later file replaces an earlier row
with the same key. This is how a rerun output root overwrites an
``InternalServerError`` row without double counting. Pass the main campaign
first, then any rerun roots that should override it.

Output: by default ``--out-json`` keeps the recomputed ``evaluation_summary``
and a compact merged-row inventory, not full per-row objects (they stay in raw
state and keep committed evidence files small). Add ``--include-rows`` to embed
the merged rows for debugging.

Example::

    python -m repopilot.recompute \\
        --title "Stage 4 - 24 tasks - luna vs sol" \\
        --out-json docs/evidence/stage4-24tasks-luna-sol-v1/recomputed.json \\
        --out-markdown docs/evidence/stage4-24tasks-luna-sol-v1/recomputed.md \\
        ~/.local/state/repopilot/campaigns/<main>/summary.json \\
        ~/.local/state/repopilot/campaigns/<rerun-a>/summary.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from repopilot.evaluation import aggregate, markdown

_ROW_KEY = ("model", "round", "task_id", "engine")


def _row_identity(row: dict[str, Any]) -> tuple[Any, ...]:
    return tuple(row.get(key) for key in _ROW_KEY)


def load_summary(path: Path) -> dict[str, Any]:
    """Load one raw campaign ``summary.json`` without touching credentials."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or "results" not in payload:
        raise ValueError(f"{path} is not a campaign summary.json (no 'results' key)")
    return payload


def merge_rows(summaries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge row-level results; later summaries override earlier rows per key.

    A later row replaces an earlier row with the same ``(model, round, task_id,
    engine)`` identity, which is how a rerun output root overwrites an
    ``InternalServerError`` row. Two guards keep the merge conservative:
    rows without a real task status never replace a row that has one, and a
    bad late row never overwrites a good one.
    """
    merged: dict[tuple[Any, ...], dict[str, Any]] = {}
    for summary in summaries:
        for row in summary.get("results", []):
            if not row.get("task_id") or not row.get("engine"):
                continue
            identity = _row_identity(row)
            if identity not in merged:
                merged[identity] = row
                continue
            previous = merged[identity]
            incoming_ok = row.get("status") is not None
            existing_ok = previous.get("status") is not None
            if incoming_ok and not existing_ok:
                merged[identity] = row  # rerun replaces a failed row
            elif incoming_ok and existing_ok:
                merged[identity] = row  # deterministic later-wins overlay
    return list(merged.values())


def row_inventory(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Compact merged-row summary so a committed file stays small."""
    from collections import Counter

    models = sorted({r.get("model", "unknown") for r in results})
    engines = sorted(e for e in {r.get("engine") for r in results} if e is not None)
    rounds = sorted(round_number for round_number in {r.get("round") for r in results} if round_number is not None)
    statuses = dict(Counter(r.get("status") for r in results))
    return {"merged_rows": len(results), "models": models, "engines": engines, "rounds": rounds, "statuses": statuses}


def recompute(
    summary_paths: list[Path],
    *,
    title: str | None = None,
    include_rows: bool = False,
) -> dict[str, Any]:
    """Merge raw campaign summaries and recompute the full evaluation summary.

    By default the returned document carries the recomputed ``evaluation_summary``
    and a compact merged-row inventory, not the full per-row objects (those stay
    in raw state; committed evidence files should stay small). Pass
    ``include_rows=True`` for debugging or for diffing against the raw
    ``summary.json`` written by the runner.
    """
    if not summary_paths:
        raise ValueError("At least one campaign summary.json is required")
    summaries = [load_summary(path) for path in summary_paths]
    configs = [summary.get("config") or {} for summary in summaries]
    config: dict[str, Any] = {}
    for candidate in configs:
        if candidate:
            config = dict(candidate)
            break
    results = merge_rows(summaries)
    document: dict[str, Any] = {
        "schema_version": 4,
        "title": title,
        "source_summaries": [str(path) for path in summary_paths],
        "config": config,
        "inventory": row_inventory(results),
        "evaluation_summary": aggregate(results),
    }
    if include_rows:
        document["results"] = results
    return document


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )


def _parser() -> argparse.ArgumentParser:
    description = (__doc__ or "").split("\n\n")[0]
    parser = argparse.ArgumentParser(
        description=description,
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("summary", nargs="+", type=Path, help="Raw campaign summary.json (main first, reruns after).")
    parser.add_argument("--title", help="Optional title stored in the output JSON.")
    parser.add_argument(
        "--out-json",
        type=Path,
        required=True,
        help="Where to write the recomputed JSON (results + evaluation_summary).",
    )
    parser.add_argument("--out-markdown", type=Path, help="Optional markdown table for the same recomputation.")
    parser.add_argument(
        "--include-rows",
        action="store_true",
        help="Embed the full merged per-row objects in the JSON output (large; debugging only).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    for path in args.summary:
        if not path.is_file():
            print(f"error: summary not found: {path}", file=sys.stderr)
            return 2
    document = recompute(args.summary, title=args.title, include_rows=args.include_rows)
    _write_json(args.out_json, document)
    summary_markdown = markdown(document["evaluation_summary"])
    if args.out_markdown:
        args.out_markdown.parent.mkdir(parents=True, exist_ok=True)
        args.out_markdown.write_text(summary_markdown, encoding="utf-8")
    group_count = len(document["evaluation_summary"]["groups"])
    paired_count = len(document["evaluation_summary"]["paired"])
    merged_rows = document["inventory"]["merged_rows"]
    print(f"merged {merged_rows} rows; {group_count} groups; {paired_count} paired categories")
    print(f"wrote {args.out_json}")
    if args.out_markdown:
        print(f"wrote {args.out_markdown}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
