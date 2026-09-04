from __future__ import annotations

import json
from pathlib import Path

from repopilot.benchmark import BenchmarkBudget, BenchmarkConfig, BenchmarkEngine, BenchmarkResult, BenchmarkRun
from repopilot.campaign import CampaignConfig, run_campaign


def test_campaign_runs_models_and_rounds_sequentially_with_safe_reports(tmp_path: Path) -> None:
    calls: list[tuple[str, Path]] = []
    api_key = "campaign-secret"
    base_url = "https://user:password@example.invalid/v1"
    config = CampaignConfig(
        output_root=tmp_path / "campaign",
        tasks_dir=tmp_path / "tasks",
        models=("gpt-5.6-luna", "vendor/other"),
        rounds=2,
        image="python:3.12-bookworm",
        budget=BenchmarkBudget(max_steps=4),
        engines=(BenchmarkEngine.BASELINE,),
        task_ids=("seed-single-file",),
        temperature=0.0,
        api_key=api_key,
        base_url=base_url,
    )

    def fake_runner(benchmark_config: BenchmarkConfig) -> BenchmarkRun:
        calls.append((benchmark_config.model.model_name, benchmark_config.output_directory))
        assert benchmark_config.model.api_key == api_key
        assert benchmark_config.model.base_url == base_url
        assert benchmark_config.model.model_kwargs == {"temperature": 0.0}
        result = BenchmarkResult(
            task_id="seed-single-file",
            engine=BenchmarkEngine.BASELINE,
            artifact_directory=benchmark_config.output_directory / "seed-single-file" / "baseline",
            status="Submitted",
            success=True,
            metrics={"steps": 2, "tokens": {"total": 9}, "cost": None, "duration_seconds": 1.5},
            verifier={"exit_code": 0},
        )
        benchmark_config.output_directory.mkdir(parents=True, exist_ok=True)
        (benchmark_config.output_directory / "config.json").write_text(
            json.dumps({"api_key": api_key, "base_url": base_url}), encoding="utf-8"
        )
        return BenchmarkRun(benchmark_config, (), (result,), benchmark_config.output_directory)

    campaign = run_campaign(config, runner=fake_runner)

    assert [model for model, _path in calls] == [
        "openai/gpt-5.6-luna",
        "openai/gpt-5.6-luna",
        "vendor/other",
        "vendor/other",
    ]
    assert calls[0][1] == tmp_path / "campaign" / "gpt-5.6-luna" / "round-001"
    assert calls[-1][1] == tmp_path / "campaign" / "vendor-other" / "round-002"
    assert len(campaign.results) == 4
    assert campaign.results[0]["model"] == "gpt-5.6-luna"
    assert campaign.results[0]["round"] == 1

    config_text = (tmp_path / "campaign" / "config.json").read_text()
    summary_text = (tmp_path / "campaign" / "summary.json").read_text()
    markdown_text = (tmp_path / "campaign" / "summary.md").read_text()
    assert api_key not in config_text + summary_text + markdown_text
    assert base_url not in config_text + summary_text + markdown_text
    assert json.loads(summary_text)["pricing_basis"]["as_of"] == "2026-09-04"
    assert "Total tokens" in markdown_text
    assert "Duration (s)" in markdown_text
    assert api_key not in (calls[0][1] / "config.json").read_text()
    assert base_url not in (calls[0][1] / "config.json").read_text()


def test_campaign_records_a_failed_round_and_continues(tmp_path: Path) -> None:
    config = CampaignConfig(
        output_directory=tmp_path / "campaign",
        tasks_directory=tmp_path / "tasks",
        models=("first", "second"),
        rounds=1,
    )
    calls: list[str] = []

    def fake_runner(benchmark_config: BenchmarkConfig) -> BenchmarkRun:
        calls.append(benchmark_config.model.model_name)
        if len(calls) == 1:
            raise RuntimeError("relay unavailable")
        return BenchmarkRun(benchmark_config, (), (), benchmark_config.output_directory)

    campaign = run_campaign(config, runner=fake_runner)

    assert calls == ["openai/first", "openai/second"]
    assert len(campaign.errors) == 1
    assert campaign.errors[0]["success"] is None
    assert campaign.errors[0]["error"] == "relay unavailable"
    assert (tmp_path / "campaign" / "first" / "round-001" / "error.json").is_file()
    summary = json.loads((tmp_path / "campaign" / "summary.json").read_text())
    assert summary["results"][0]["success"] is None
    assert summary["results"][1:] == []
