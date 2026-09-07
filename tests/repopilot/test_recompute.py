"""Tests for offline evidence recomputation (repopilot.recompute)."""

from __future__ import annotations

import json

import pytest

from repopilot.recompute import load_summary, merge_rows, recompute


def _row(
    task_id: str,
    engine: str,
    *,
    model: str = "gpt-a",
    round: int = 1,
    status: str | None = "Submitted",
    task_pass: bool | None = True,
    repository_pass: bool | None = True,
    category: str = "recovery",
    metrics: dict | None = None,
) -> dict:
    return {
        "model": model,
        "round": round,
        "repeat": round,
        "task_id": task_id,
        "engine": engine,
        "category": category,
        "capabilities": ["recovery"],
        "status": status,
        "task_pass": task_pass,
        "repository_pass": repository_pass,
        "metrics": metrics if metrics is not None else {"tokens": {"total": 10}, "llm_calls": 1},
        "evaluation": {
            "termination": "correct_success" if task_pass else "correct_failure",
            "recovery": {"trigger_count": 0, "attempt_count": 0, "resolved_count": 0, "failure_types": []},
            "churn": {"status": "unsupported"},
        },
    }


def _summary(rows: list[dict], models: list[str] | None = None) -> dict:
    return {"config": {"models": models or ["gpt-a"], "rounds": 3}, "results": rows}


def test_merge_rows_keeps_distinct_trials_and_dedupes_by_identity(tmp_path):
    a = _summary([_row("t1", "baseline"), _row("t1", "repopilot")])
    b = _summary([_row("t2", "baseline")])
    merged = merge_rows([a, b])
    assert len(merged) == 3


def test_merge_rows_later_summary_overrides_failed_row(tmp_path):
    failed = _row("t1", "baseline", status="InternalServerError", task_pass=None, repository_pass=None)
    clean = _row("t1", "baseline", status="Submitted", task_pass=True)
    merged = merge_rows([_summary([failed]), _summary([clean])])
    assert len(merged) == 1
    assert merged[0]["status"] == "Submitted"
    assert merged[0]["task_pass"] is True


def test_merge_rows_does_not_replace_good_row_with_broken_late_row(tmp_path):
    clean = _row("t1", "baseline", status="Submitted", task_pass=True)
    broken = _row("t1", "baseline", status=None, task_pass=None)
    merged = merge_rows([_summary([clean]), _summary([broken])])
    assert merged[0]["status"] == "Submitted"


def test_load_summary_rejects_non_campaign_json(tmp_path):
    path = tmp_path / "not-summary.json"
    path.write_text(json.dumps({"foo": 1}), encoding="utf-8")
    with pytest.raises(ValueError):
        load_summary(path)


def test_recompute_requires_at_least_one_summary(tmp_path):
    with pytest.raises(ValueError, match="At least one"):
        recompute([])


def test_recompute_builds_full_evaluation_summary(tmp_path, monkeypatch):
    # Give recompute a location to read from without real state dirs.
    main = tmp_path / "main" / "summary.json"
    main.parent.mkdir(parents=True)
    main.write_text(
        json.dumps(
            _summary(
                [
                    # Round 1 gpt-a crashed on the provider side; the rerun root fixes it.
                    _row("t1", "baseline", model="gpt-a", status="InternalServerError", task_pass=None, repository_pass=None, round=1),
                    _row("t1", "baseline", model="gpt-a", task_pass=True, round=2),
                    _row("t1", "repopilot", model="gpt-a", task_pass=True, round=1),
                    _row("t1", "baseline", model="gpt-b", task_pass=False, round=1),
                ]
            )
        ),
        encoding="utf-8",
    )
    rerun = tmp_path / "rerun" / "summary.json"
    rerun.parent.mkdir(parents=True)
    rerun.write_text(
        json.dumps(
            _summary([_row("t1", "baseline", model="gpt-a", status="Submitted", task_pass=True, round=1)])
        ),
        encoding="utf-8",
    )
    document = recompute([main, rerun])
    summary = document["evaluation_summary"]
    assert summary["schema_version"] >= 4
    # The broken row was replaced so the merged inventory reports a clean row.
    assert document["inventory"]["merged_rows"] == 4
    assert any(g["model"] == "gpt-a" and g["dimension"] == "category" for g in summary["groups"])
    assert any(g["dimension"] == "capability" for g in summary["groups"])
    assert summary["paired"]  # paired outcome rows present
    # Full rows are opt-in to keep committed files small.
    assert "results" not in document
    document_rows = recompute([main, rerun], include_rows=True)
    assert len(document_rows["results"]) == 4
    assert any(r["status"] == "Submitted" for r in document_rows["results"])
