"""Apply preselected replacements deterministically, retaining all original outcomes."""

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def identity(row):
    return row["model"], row["arm"], row["task"]


def main():
    original = json.loads((HERE / "audit.json").read_text())
    replacement = json.loads((HERE / "replacement-audit.json").read_text())
    plan = json.loads((HERE / "replacement-plan.json").read_text())
    assert original["completed_runs"] == 24 and replacement["completed_runs"] == plan["selected_count"]
    assert all(a["input_integrity"] and a["unique_run_ids"] and not a["violations"] for a in [original, replacement])
    selected = {(r["model"], r["variant"], r["task"]): r for r in plan["selected"]}
    replacements = {identity(r): r for r in replacement["rows"]}
    assert set(replacements) == set(selected)
    effective = []
    comparisons = []
    for row in original["rows"]:
        key = identity(row)
        if key in selected:
            assert selected[key]["original_run_id"] == row["run_id"]
            new = replacements[key]
            comparisons.append(
                {
                    "model": key[0],
                    "arm": key[1],
                    "task": key[2],
                    "original": row,
                    "replacement": new,
                    "reason": selected[key],
                }
            )
            effective.append(new)
        else:
            effective.append(row)
    report = {
        **original,
        "rows": effective,
        "selection": "Preselected replacement regardless of outcome; no best-of selection.",
        "retained_attempts": len(original["rows"]) + len(replacement["rows"]),
        "replacement_count": len(replacements),
    }
    (HERE / "effective-audit.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    (HERE / "replacement-comparison.json").write_text(json.dumps(comparisons, indent=2, ensure_ascii=False) + "\n")
    print("Finalized", len(effective), "cells from", report["retained_attempts"], "retained attempts")


if __name__ == "__main__":
    main()
