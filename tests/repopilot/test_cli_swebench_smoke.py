from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from repopilot.cli import create_app
from repopilot.swebench_smoke import INSTANCE_ID, SWEbenchSmokeResult


def _result(config, *, status: str = "ENVIRONMENT_UNAVAILABLE") -> SWEbenchSmokeResult:
    artifact_directory = config.output_directory / INSTANCE_ID
    return SWEbenchSmokeResult(
        instance_id=INSTANCE_ID,
        status=status,
        success=None,
        artifact_directory=artifact_directory,
        metrics={"model_calls": 0, "cost_usd": None},
        preflight={"status": status, "image": config.image},
        verifier=None,
        error="Docker image is not available locally.",
    )


def test_cli_swebench_smoke_builds_bounded_configuration(tmp_path: Path) -> None:
    received = []

    def fake_runner(config):
        received.append(config)
        return _result(config)

    result = CliRunner().invoke(
        create_app(smoke_runner=fake_runner),
        [
            "swebench-smoke",
            "--state-dir",
            str(tmp_path),
            "--model",
            "provider/fixed-model",
            "--api-key",
            "test-secret",
            "--base-url",
            "https://provider.example/v1",
            "--image",
            "local/swebench:latest",
            "--temperature",
            "0.1",
            "--max-steps",
            "7",
            "--max-replans",
            "1",
            "--max-consecutive-failures",
            "2",
            "--command-timeout-seconds",
            "21",
            "--max-run-seconds",
            "90",
            "--max-cost-usd",
            "1.5",
            "--verifier-timeout-seconds",
            "120",
        ],
    )

    assert result.exit_code == 0, result.output
    assert len(received) == 1
    config = received[0]
    assert config.output_directory.parent == tmp_path
    assert config.model_name == "provider/fixed-model"
    assert config.model_kwargs == {"temperature": 0.1}
    assert config.image == "local/swebench:latest"
    assert config.max_steps == 7
    assert config.max_replans == 1
    assert config.max_consecutive_failures == 2
    assert config.command_timeout_seconds == 21.0
    assert config.max_run_seconds == 90.0
    assert config.max_cost_usd == 1.5
    assert config.max_workers == 1
    assert config.verifier_timeout_seconds == 120.0


def test_cli_swebench_smoke_prints_environment_status_and_artifacts(tmp_path: Path) -> None:
    received = []

    def fake_runner(config):
        received.append(config)
        return _result(config)

    result = CliRunner().invoke(
        create_app(smoke_runner=fake_runner),
        ["swebench-smoke", "--state-dir", str(tmp_path)],
    )

    assert result.exit_code == 0, result.output
    assert received[0].max_steps == 50
    assert "ENVIRONMENT_UNAVAILABLE" in result.output
    assert "Artifacts:" in result.output
    assert INSTANCE_ID in result.output
