from __future__ import annotations

from pathlib import Path

from click.utils import strip_ansi
from typer.testing import CliRunner

from repopilot.benchmark import DEFAULT_BENCHMARK_IMAGE, BenchmarkEngine, BenchmarkResult, BenchmarkRun
from repopilot.cli import create_app
from repopilot.environment import DockerProxyMode


def test_cli_builds_one_shared_docker_benchmark_configuration(tmp_path: Path) -> None:
    received = []

    def fake_runner(config):
        received.append(config)
        result = BenchmarkResult(
            task_id="seed-single-file",
            engine=BenchmarkEngine.REPOPILOT,
            artifact_directory=config.output_directory / "seed-single-file" / "repopilot",
            status="SUCCEEDED",
            success=True,
            metrics={},
            verifier={"exit_code": 0},
        )
        return BenchmarkRun(config, (), (result,), config.output_directory)

    result = CliRunner().invoke(
        create_app(benchmark_runner=fake_runner),
        [
            "benchmark",
            "--state-dir",
            str(tmp_path / "benchmarks"),
            "--model",
            "provider/fixed-model",
            "--engine",
            "repopilot",
            "--task",
            "seed-single-file",
            "--image",
            "python:3.12-bookworm",
            "--docker-proxy-mode",
            "explicit",
            "--docker-proxy-url",
            "http://proxy.example:8080",
            "--temperature",
            "0.2",
            "--max-steps",
            "7",
            "--max-replans",
            "3",
            "--max-consecutive-failures",
            "4",
            "--command-timeout-seconds",
            "21",
            "--max-run-seconds",
            "90",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "seed-single-file / repopilot: repository passed" in result.output
    assert len(received) == 1
    config = received[0]
    assert config.engines == (BenchmarkEngine.REPOPILOT,)
    assert config.task_ids == ("seed-single-file",)
    assert config.model.model_name == "provider/fixed-model"
    assert config.model.model_kwargs == {"temperature": 0.2}
    assert config.repeats == 3
    assert config.image == "python:3.12-bookworm"
    assert config.proxy_mode is DockerProxyMode.EXPLICIT
    assert config.proxy_url == "http://proxy.example:8080"
    assert config.public_dict()["proxy_mode"] == "explicit"
    assert "proxy.example" not in str(config.public_dict())
    assert config.budget.max_steps == 7
    assert config.budget.max_replans == 3
    assert config.budget.max_consecutive_failures == 4
    assert config.budget.command_timeout_seconds == 21.0
    assert config.budget.max_run_seconds == 90.0


def test_cli_benchmark_defaults_to_both_engines_and_requires_a_model(tmp_path: Path) -> None:
    received = []

    def fake_runner(config):
        received.append(config)
        return BenchmarkRun(config, (), (), config.output_directory)

    missing_model = CliRunner().invoke(
        create_app(benchmark_runner=fake_runner),
        ["benchmark", "--state-dir", str(tmp_path)],
    )
    assert missing_model.exit_code == 2
    assert "Provide --model" in strip_ansi(missing_model.output)

    result = CliRunner().invoke(
        create_app(benchmark_runner=fake_runner),
        ["benchmark", "--state-dir", str(tmp_path), "--model", "provider/fixed-model"],
    )
    assert result.exit_code == 0, result.output
    assert received[0].engines == (BenchmarkEngine.BASELINE, BenchmarkEngine.REPOPILOT)
    assert received[0].image == DEFAULT_BENCHMARK_IMAGE

    missing_proxy_url = CliRunner().invoke(
        create_app(benchmark_runner=fake_runner),
        [
            "benchmark",
            "--state-dir",
            str(tmp_path),
            "--model",
            "provider/fixed-model",
            "--docker-proxy-mode",
            "explicit",
        ],
    )
    assert missing_proxy_url.exit_code == 2
    assert "--docker-proxy-url" in strip_ansi(missing_proxy_url.output)
