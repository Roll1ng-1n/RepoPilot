from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from repopilot.campaign import CampaignRun
from repopilot.cli import create_app
from repopilot.model_probe import ProbeAttempt, ProbeReport, ProbeResult


def test_cli_probe_loads_credentials_from_env_file_and_writes_reports(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Upstream imports (e.g. LiteLLM) can load a workspace/global .env into
    # os.environ during collection; without clearing these, typer's envvar
    # defaults would win over the --env-file under test and make this test
    # order-dependent. Isolate the process env for the probe invocation.
    monkeypatch.delenv("REPOPILOT_API_KEY", raising=False)
    monkeypatch.delenv("REPOPILOT_BASE_URL", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("REPOPILOT_API_KEY=test-secret\nREPOPILOT_BASE_URL=https://relay.invalid/v1\n")
    received = []

    def fake_probe(models, **kwargs):
        received.append((models, kwargs))
        passed = ProbeAttempt(valid=True, duration_seconds=0.1)
        return ProbeReport(tuple(ProbeResult(model, passed, passed) for model in models))

    result = CliRunner().invoke(
        create_app(probe_runner=fake_probe),
        [
            "probe",
            "--state-dir",
            str(tmp_path / "probes"),
            "--env-file",
            str(env_file),
            "--model",
            "gpt-5.6-luna",
            "--model",
            "gpt-5.5",
        ],
    )

    assert result.exit_code == 0, result.output
    assert received[0][0] == ("gpt-5.6-luna", "gpt-5.5")
    assert received[0][1]["api_key"] == "test-secret"
    assert received[0][1]["base_url"] == "https://relay.invalid/v1"
    assert "test-secret" not in result.output
    output_directory = next((tmp_path / "probes").iterdir())
    assert (output_directory / "summary.json").is_file()
    assert (output_directory / "summary.md").is_file()


def test_cli_campaign_builds_multi_model_paired_configuration(tmp_path: Path) -> None:
    received = []

    def fake_campaign(config):
        received.append(config)
        config.output_directory.mkdir(parents=True)
        return CampaignRun(config, (), config.output_directory)

    result = CliRunner().invoke(
        create_app(campaign_runner=fake_campaign),
        [
            "campaign",
            "--state-dir",
            str(tmp_path / "campaigns"),
            "--api-key",
            "test-secret",
            "--base-url",
            "https://relay.invalid/v1",
            "--model",
            "gpt-5.6-luna",
            "--model",
            "gpt-5.5",
            "--rounds",
            "2",
            "--task",
            "seed-single-file",
            "--engine",
            "baseline",
        ],
    )

    assert result.exit_code == 0, result.output
    config = received[0]
    assert config.models == ("gpt-5.6-luna", "gpt-5.5")
    assert config.rounds == 2
    assert config.task_ids == ("seed-single-file",)
    assert [engine.value for engine in config.engines] == ["baseline"]
    assert config.api_key == "test-secret"
    assert "test-secret" not in result.output
