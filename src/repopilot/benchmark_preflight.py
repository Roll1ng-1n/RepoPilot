"""No-model Docker identity and capability checks for benchmark execution."""

from __future__ import annotations

import json
import os
import subprocess
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any

from repopilot.benchmark_reporting import _benchmark_secret_values, _redact_benchmark_value, _text
from repopilot.environment import docker_proxy_run_args

if TYPE_CHECKING:
    from repopilot.benchmark import BenchmarkConfig


@dataclass(frozen=True)
class BenchmarkPreflight:
    """No-model Docker checks for one paired benchmark invocation."""

    status: str
    image: str
    resolved_image: str | None
    image_id: str | None
    image_digest: str | None
    checks: tuple[dict[str, Any], ...]
    error: str | None = None

    @property
    def ready(self) -> bool:
        return self.status == "READY"

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "image": self.image,
            "resolved_image": self.resolved_image,
            "image_id": self.image_id,
            "image_digest": self.image_digest,
            "checks": list(self.checks),
            "error": self.error,
        }


def preflight_benchmark_image(
    config: BenchmarkConfig,
    *,
    command_runner: Callable[[list[str], float], subprocess.CompletedProcess[str]] | None = None,
) -> BenchmarkPreflight:
    """Resolve and validate the Docker image before any model is created.

    ``docker image inspect`` supplies a content-addressed local image ID.  The
    ID is used for both engines so a mutable tag cannot change between the
    baseline and RepoPilot attempts.  A registry RepoDigest is retained when
    Docker reports one, but locally built images need not have one.
    """

    run_command = command_runner or _run_benchmark_command
    docker = os.environ.get("MSWEA_DOCKER_EXECUTABLE", "docker")
    checks: list[dict[str, Any]] = []
    proxy_args: list[str]
    try:
        proxy_args = docker_proxy_run_args(config.proxy_mode, config.proxy_url)
    except (TypeError, ValueError) as error:
        return BenchmarkPreflight("ENVIRONMENT_UNAVAILABLE", config.image, None, None, None, (), str(error))
    proxy_secrets = _benchmark_secret_values(config)

    # Restrict inspect output to identity fields. Full image metadata may
    # contain build environment details and is not useful benchmark evidence.
    inspect_argv = [
        docker,
        "image",
        "inspect",
        '--format={"Id":{{json .Id}},"RepoDigests":{{json .RepoDigests}}}',
        config.image,
    ]
    inspected, inspect_error = _run_preflight_check(
        "image_inspect", inspect_argv, config.budget.command_timeout_seconds, run_command, proxy_secrets
    )
    checks.append(inspected)
    if inspect_error is not None or inspected["exit_code"] != 0:
        detail = inspect_error or inspected.get("stderr") or "Docker image is not available locally."
        return BenchmarkPreflight(
            "ENVIRONMENT_UNAVAILABLE",
            config.image,
            None,
            None,
            None,
            tuple(checks),
            _redact_benchmark_value(str(detail), proxy_secrets),
        )

    try:
        image_id, image_digest = _parse_image_inspection(inspected.get("stdout", ""))
    except ValueError as error:
        return BenchmarkPreflight("ENVIRONMENT_UNAVAILABLE", config.image, None, None, None, tuple(checks), str(error))

    for command_name, command in (
        ("python", "python --version"),
        ("git", "git --version"),
    ):
        argv = [docker, "run", "--rm", "--pull=never", *proxy_args, image_id, *command.split()]
        check, check_error = _run_preflight_check(
            command_name, argv, config.budget.command_timeout_seconds, run_command, proxy_secrets
        )
        checks.append(check)
        if check_error is not None or check["exit_code"] != 0:
            detail = check_error or check.get("stderr") or f"Docker image does not provide {command.split()[0]}."
            return BenchmarkPreflight(
                "ENVIRONMENT_UNAVAILABLE",
                config.image,
                image_id,
                image_id,
                image_digest,
                tuple(checks),
                _redact_benchmark_value(str(detail), proxy_secrets),
            )

    return BenchmarkPreflight("READY", config.image, image_id, image_id, image_digest, tuple(checks))


def _run_benchmark_command(argv: list[str], timeout: float) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, capture_output=True, check=False, text=True, timeout=timeout)


def _run_preflight_check(
    name: str,
    argv: list[str],
    timeout: float,
    command_runner: Callable[[list[str], float], subprocess.CompletedProcess[str]],
    secrets: Sequence[str],
) -> tuple[dict[str, Any], str | None]:
    started = time.monotonic()
    error: str | None = None
    try:
        completed = command_runner(argv, timeout)
        stdout = _text(completed.stdout)
        stderr = _text(completed.stderr)
        exit_code = completed.returncode
    except subprocess.TimeoutExpired as exception:
        stdout = _text(exception.stdout)
        stderr = _text(exception.stderr)
        exit_code = -1
        error = f"Command timed out after {timeout} seconds."
    except (OSError, subprocess.SubprocessError) as exception:
        stdout = ""
        stderr = str(exception)
        exit_code = -1
        error = str(exception) or type(exception).__name__
    check = {
        "name": name,
        "command": _redact_benchmark_value(argv, secrets),
        "exit_code": exit_code,
        "stdout": _redact_benchmark_value(stdout, secrets),
        "stderr": _redact_benchmark_value(stderr, secrets),
        "duration_seconds": time.monotonic() - started,
    }
    return check, error


def _redact_preflight_result(preflight: BenchmarkPreflight, config: BenchmarkConfig) -> BenchmarkPreflight:
    try:
        secrets = _benchmark_secret_values(config)
    except (TypeError, ValueError):
        secrets = []
    return replace(
        preflight,
        checks=tuple(_redact_benchmark_value(check, secrets) for check in preflight.checks),
        error=_redact_benchmark_value(preflight.error, secrets),
    )


def _parse_image_inspection(output: str) -> tuple[str, str | None]:
    try:
        payload = json.loads(output)
    except (TypeError, json.JSONDecodeError) as error:
        raise ValueError("Docker image inspection returned invalid JSON.") from error
    if isinstance(payload, list):
        payload = payload[0] if payload else None
    if not isinstance(payload, Mapping):
        raise ValueError("Docker image inspection returned no image metadata.")
    image_id = payload.get("Id", payload.get("ID"))
    if not isinstance(image_id, str) or not image_id.strip():
        raise ValueError("Docker image inspection returned no immutable image ID.")
    image_id = image_id.strip()
    repo_digests = payload.get("RepoDigests")
    image_digest = (
        next(
            (value.strip() for value in repo_digests if isinstance(value, str) and value.strip()),
            None,
        )
        if isinstance(repo_digests, list)
        else None
    )
    return image_id, image_digest
