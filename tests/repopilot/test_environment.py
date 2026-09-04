"""Execution Environment contracts and composition tests."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

import repopilot.environment as environment_module
from repopilot.environment import (
    Command,
    DockerExecutionEnvironment,
    DockerProxyMode,
    EnvironmentCreationError,
    EnvironmentRequest,
    LocalExecutionEnvironment,
    create_execution_environment,
)

# The full bookworm image is built from buildpack-deps:bookworm, whose SCM
# layer installs git; Debian also supplies the bash used by Repository Tools.
DOCKER_TEST_IMAGE = os.environ.get("REPOPILOT_DOCKER_TEST_IMAGE", "python:3.12-bookworm")


def _docker_available() -> bool:
    executable = shutil.which("docker")
    if executable is None:
        return False
    try:
        subprocess.run([executable, "version"], capture_output=True, check=True, timeout=5)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return False
    return True


@pytest.fixture(
    params=[
        "local",
        pytest.param("docker", marks=pytest.mark.skipif(not _docker_available(), reason="Docker is unavailable")),
    ]
)
def execution_environment(request: pytest.FixtureRequest, tmp_path: Path):
    target_repository = tmp_path / "target"
    target_repository.mkdir()
    if request.param == "local":
        environment = LocalExecutionEnvironment(target_repository, maximum_output_characters=5)
    else:
        environment = DockerExecutionEnvironment(
            target_repository,
            image=DOCKER_TEST_IMAGE,
            maximum_output_characters=5,
        )
    try:
        yield environment
    finally:
        environment.close()


def test_execution_environments_share_command_contract(execution_environment) -> None:
    result = execution_environment.execute(Command(("sh", "-c", "printf stdout; printf stderr >&2")))

    assert result.exit_code == 0
    assert result.stdout == "stdou"
    assert result.stderr == "stder"
    assert result.truncated is True

    stdin_result = execution_environment.execute(
        Command(("sh", "-c", "read value; printf 'in:%s' \"$value\""), stdin="needle\n")
    )

    assert stdin_result.exit_code == 0
    assert stdin_result.stdout == "in:ne"
    assert stdin_result.stderr == ""
    assert stdin_result.truncated is True

    timeout_result = execution_environment.execute(Command(("sh", "-c", "sleep 1"), timeout_seconds=0.01))

    assert timeout_result.exit_code == -1
    assert "timed out" in timeout_result.stderr
    assert timeout_result.truncated is True


def test_docker_adapter_reuses_upstream_lifecycle_and_preserves_streams(monkeypatch, tmp_path: Path) -> None:
    lifecycle_calls: list[dict[str, object]] = []
    subprocess_calls: list[tuple[list[str], dict[str, object]]] = []

    class UpstreamDockerDouble:
        def __init__(self, **kwargs: object) -> None:
            lifecycle_calls.append(kwargs)
            self.config = SimpleNamespace(executable="docker", cwd="/workspace")
            self.container_id = "container-id"

    def run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        subprocess_calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0, stdout="stdout", stderr="stderr")

    monkeypatch.setattr(environment_module, "DockerEnvironment", UpstreamDockerDouble)
    monkeypatch.setattr(environment_module.subprocess, "run", run)
    target_repository = tmp_path / "target"
    target_repository.mkdir()
    environment = DockerExecutionEnvironment(target_repository, image="test-image", maximum_output_characters=20)

    result = environment.execute(Command(("sh", "-c", "printf ignored"), stdin="input"))
    environment.close()
    environment.close()

    assert result.exit_code == 0
    assert result.stdout == "stdout"
    assert result.stderr == "stderr"
    assert result.truncated is False
    assert lifecycle_calls == [
        {
            "image": "test-image",
            "cwd": "/workspace",
            "run_args": (
                [
                    "--rm",
                    "--mount",
                    f"type=bind,source={target_repository.resolve()},target=/workspace",
                ]
                + ([f"--user={os.getuid()}:{os.getgid()}"] if hasattr(os, "getuid") else [])
            ),
        }
    ]
    assert subprocess_calls == [
        (
            ["docker", "exec", "-i", "-w", "/workspace", "container-id", "sh", "-c", "printf ignored"],
            {
                "capture_output": True,
                "check": False,
                "input": "input",
                "text": True,
                "timeout": 30.0,
            },
        ),
        (["docker", "rm", "-f", "container-id"], {"capture_output": True, "check": False, "timeout": 60}),
    ]


def test_docker_proxy_none_does_not_add_container_proxy_arguments(monkeypatch, tmp_path: Path) -> None:
    lifecycle_calls: list[dict[str, object]] = []

    class UpstreamDockerDouble:
        def __init__(self, **kwargs: object) -> None:
            lifecycle_calls.append(kwargs)
            self.config = SimpleNamespace(executable="docker", cwd="/workspace")
            self.container_id = "container-id"

    monkeypatch.setattr(environment_module, "DockerEnvironment", UpstreamDockerDouble)
    target_repository = tmp_path / "target"
    target_repository.mkdir()

    DockerExecutionEnvironment(target_repository, image="test-image")

    assert lifecycle_calls[0]["run_args"] == [
        "--rm",
        "--mount",
        f"type=bind,source={target_repository.resolve()},target=/workspace",
        *([f"--user={os.getuid()}:{os.getgid()}"] if hasattr(os, "getuid") else []),
    ]


def test_docker_proxy_inherit_rewrites_loopback_and_adds_linux_host_gateway(monkeypatch, tmp_path: Path) -> None:
    lifecycle_calls: list[dict[str, object]] = []

    class UpstreamDockerDouble:
        def __init__(self, **kwargs: object) -> None:
            lifecycle_calls.append(kwargs)
            self.config = SimpleNamespace(executable="docker", cwd="/workspace")
            self.container_id = "container-id"

    monkeypatch.setattr(environment_module, "DockerEnvironment", UpstreamDockerDouble)
    monkeypatch.setattr(environment_module.platform, "system", lambda: "Linux")
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:7897")
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.example:8443")
    monkeypatch.delenv("ALL_PROXY", raising=False)
    monkeypatch.delenv("NO_PROXY", raising=False)
    target_repository = tmp_path / "target"
    target_repository.mkdir()

    DockerExecutionEnvironment(target_repository, image="test-image", proxy_mode=DockerProxyMode.INHERIT)

    run_args = lifecycle_calls[0]["run_args"]
    assert "--add-host=host.docker.internal:host-gateway" in run_args
    assert "--env" in run_args
    assert "HTTP_PROXY=http://host.docker.internal:7897" in run_args
    assert "HTTPS_PROXY=http://proxy.example:8443" in run_args


def test_docker_proxy_explicit_sets_proxy_variables_without_persisting_url(monkeypatch, tmp_path: Path) -> None:
    lifecycle_calls: list[dict[str, object]] = []

    class UpstreamDockerDouble:
        def __init__(self, **kwargs: object) -> None:
            lifecycle_calls.append(kwargs)
            self.config = SimpleNamespace(executable="docker", cwd="/workspace")
            self.container_id = "container-id"

    monkeypatch.setattr(environment_module, "DockerEnvironment", UpstreamDockerDouble)
    target_repository = tmp_path / "target"
    target_repository.mkdir()
    proxy_url = "https://user:secret@proxy.example:8443"

    DockerExecutionEnvironment(
        target_repository,
        image="test-image",
        proxy_mode="explicit",
        proxy_url=proxy_url,
    )

    run_args = lifecycle_calls[0]["run_args"]
    assert "--env" in run_args
    assert "HTTP_PROXY=https://user:secret@proxy.example:8443" in run_args
    assert "HTTPS_PROXY=https://user:secret@proxy.example:8443" in run_args
    assert "ALL_PROXY=https://user:secret@proxy.example:8443" in run_args
    request = EnvironmentRequest(
        target_repository=target_repository,
        image="test-image",
        proxy_mode="explicit",
        proxy_url=proxy_url,
    )
    assert request.proxy_mode == DockerProxyMode.EXPLICIT
    assert proxy_url not in request.__repr__()


def test_docker_proxy_rejects_explicit_without_url(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="explicit.*proxy URL"):
        DockerExecutionEnvironment(tmp_path, image="test-image", proxy_mode="explicit")


def test_docker_proxy_rejects_inherited_loopback_without_a_scheme(monkeypatch, tmp_path: Path) -> None:
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("HTTP_PROXY", "127.0.0.1:7897")

    with pytest.raises(ValueError, match="include a scheme"):
        DockerExecutionEnvironment(tmp_path, image="test-image", proxy_mode="inherit")


def test_environment_factory_requires_a_docker_image(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="requires an image"):
        create_execution_environment(EnvironmentRequest(target_repository=tmp_path, environment="docker"))


def test_environment_factory_reports_docker_failure_without_local_fallback(monkeypatch, tmp_path: Path) -> None:
    class UnavailableDocker:
        def __init__(self, *_: object, **__: object) -> None:
            raise FileNotFoundError("docker")

    monkeypatch.setattr(environment_module, "DockerExecutionEnvironment", UnavailableDocker)

    with pytest.raises(EnvironmentCreationError, match="Unable to start Docker Environment"):
        create_execution_environment(
            EnvironmentRequest(target_repository=tmp_path, environment="docker", image="test-image")
        )


def test_environment_request_defaults_to_docker_for_future_benchmarks(tmp_path: Path) -> None:
    request = EnvironmentRequest(target_repository=tmp_path)

    assert request.environment == "docker"
