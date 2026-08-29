"""Execution Environment port, composition seam, and concrete backends."""

from __future__ import annotations

import os
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from minisweagent.environments.docker import DockerEnvironment

DEFAULT_MAXIMUM_OUTPUT_CHARACTERS = 20_000
CONTAINER_REPOSITORY_PATH = "/workspace"


@dataclass(frozen=True)
class Command:
    """A command requested by a Repository Tool."""

    argv: tuple[str, ...]
    timeout_seconds: float = 30.0
    stdin: str | None = None


@dataclass(frozen=True)
class CommandResult:
    """The structured observation from executing one command."""

    exit_code: int
    stdout: str
    stderr: str
    duration_seconds: float
    truncated: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "exit_code": self.exit_code,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "duration_seconds": self.duration_seconds,
            "truncated": self.truncated,
        }


class ExecutionEnvironment(Protocol):
    """Replaceable backend used by Repository Tools, never by the Runtime directly."""

    def execute(self, command: Command) -> CommandResult: ...

    def close(self) -> None: ...


@dataclass(frozen=True)
class EnvironmentRequest:
    """Composition input for an Execution Environment.

    The request defaults to Docker so a future Agent Benchmark can use its
    intended backend without a separate configuration model. Product callers,
    including the CLI, select their default explicitly.
    """

    target_repository: Path
    environment: str = "docker"
    image: str | None = None
    maximum_output_characters: int = DEFAULT_MAXIMUM_OUTPUT_CHARACTERS


class EnvironmentCreationError(RuntimeError):
    """An explicitly selected Execution Environment could not be started."""


ExecutionEnvironmentFactory = Callable[[EnvironmentRequest], ExecutionEnvironment]


class LocalExecutionEnvironment:
    """Runs commands directly in one target repository."""

    def __init__(self, target_repository: Path, *, maximum_output_characters: int = DEFAULT_MAXIMUM_OUTPUT_CHARACTERS):
        self._target_repository = target_repository.resolve()
        self._maximum_output_characters = maximum_output_characters

    def execute(self, command: Command) -> CommandResult:
        started_at = time.monotonic()
        try:
            completed = subprocess.run(
                command.argv,
                cwd=self._target_repository,
                capture_output=True,
                check=False,
                input=command.stdin,
                text=True,
                timeout=command.timeout_seconds,
            )
            stdout, stdout_truncated = self._truncate(completed.stdout)
            stderr, stderr_truncated = self._truncate(completed.stderr)
            return CommandResult(
                exit_code=completed.returncode,
                stdout=stdout,
                stderr=stderr,
                duration_seconds=time.monotonic() - started_at,
                truncated=stdout_truncated or stderr_truncated,
            )
        except subprocess.TimeoutExpired as error:
            stdout, _ = self._truncate(self._as_text(error.stdout))
            stderr, _ = self._truncate(self._as_text(error.stderr))
            return CommandResult(
                exit_code=-1,
                stdout=stdout,
                stderr=stderr or f"Command timed out after {command.timeout_seconds} seconds.",
                duration_seconds=time.monotonic() - started_at,
                truncated=True,
            )
        except OSError as error:
            return CommandResult(
                exit_code=-1,
                stdout="",
                stderr=str(error),
                duration_seconds=time.monotonic() - started_at,
                truncated=False,
            )

    def close(self) -> None:
        """Local commands have no long-lived resource to close."""

    def _truncate(self, value: str) -> tuple[str, bool]:
        if len(value) <= self._maximum_output_characters:
            return value, False
        return value[: self._maximum_output_characters], True

    @staticmethod
    def _as_text(value: str | bytes | None) -> str:
        if isinstance(value, bytes):
            return value.decode(errors="replace")
        return value or ""


class DockerExecutionEnvironment:
    """Run commands in an upstream-managed container with the Target Repository mounted.

    This adapter intentionally reuses mini-SWE-agent's Docker lifecycle. Its
    command interface cannot preserve separate stdout and stderr or stdin, so
    RepoPilot invokes ``docker exec`` directly for the Command contract.
    """

    def __init__(
        self,
        target_repository: Path,
        *,
        image: str,
        maximum_output_characters: int = DEFAULT_MAXIMUM_OUTPUT_CHARACTERS,
        executable: str | None = None,
    ):
        self._maximum_output_characters = maximum_output_characters
        self._closed = False
        target = target_repository.resolve()
        run_args = [
            "--rm",
            "--mount",
            f"type=bind,source={target},target={CONTAINER_REPOSITORY_PATH}",
        ]
        if host_identity := self._host_identity():
            run_args.append(f"--user={host_identity}")
        if executable is not None:
            self._docker = DockerEnvironment(
                image=image,
                cwd=CONTAINER_REPOSITORY_PATH,
                run_args=run_args,
                executable=executable,
            )
        else:
            self._docker = DockerEnvironment(
                image=image,
                cwd=CONTAINER_REPOSITORY_PATH,
                run_args=run_args,
            )

    def execute(self, command: Command) -> CommandResult:
        if self._closed or self._docker.container_id is None:
            return CommandResult(
                exit_code=-1,
                stdout="",
                stderr="Docker Environment is closed.",
                duration_seconds=0.0,
                truncated=False,
            )
        started_at = time.monotonic()
        invocation = [
            self._docker.config.executable,
            "exec",
            "-i",
            "-w",
            self._docker.config.cwd,
            self._docker.container_id,
            *command.argv,
        ]
        try:
            completed = subprocess.run(
                invocation,
                capture_output=True,
                check=False,
                input=command.stdin,
                text=True,
                timeout=command.timeout_seconds,
            )
            stdout, stdout_truncated = self._truncate(completed.stdout)
            stderr, stderr_truncated = self._truncate(completed.stderr)
            return CommandResult(
                exit_code=completed.returncode,
                stdout=stdout,
                stderr=stderr,
                duration_seconds=time.monotonic() - started_at,
                truncated=stdout_truncated or stderr_truncated,
            )
        except subprocess.TimeoutExpired as error:
            stdout, _ = self._truncate(self._as_text(error.stdout))
            stderr, _ = self._truncate(self._as_text(error.stderr))
            return CommandResult(
                exit_code=-1,
                stdout=stdout,
                stderr=stderr or f"Command timed out after {command.timeout_seconds} seconds.",
                duration_seconds=time.monotonic() - started_at,
                truncated=True,
            )
        except OSError as error:
            return CommandResult(
                exit_code=-1,
                stdout="",
                stderr=str(error),
                duration_seconds=time.monotonic() - started_at,
                truncated=False,
            )

    def close(self) -> None:
        """Best-effort, idempotent cleanup of the upstream-managed container."""
        if self._closed:
            return
        self._closed = True
        container_id = self._docker.container_id
        self._docker.container_id = None
        if container_id is None:
            return
        try:
            subprocess.run(
                [self._docker.config.executable, "rm", "-f", container_id],
                capture_output=True,
                check=False,
                timeout=60,
            )
        except (OSError, subprocess.SubprocessError):
            pass

    def _truncate(self, value: str) -> tuple[str, bool]:
        if len(value) <= self._maximum_output_characters:
            return value, False
        return value[: self._maximum_output_characters], True

    @staticmethod
    def _as_text(value: str | bytes | None) -> str:
        if isinstance(value, bytes):
            return value.decode(errors="replace")
        return value or ""

    @staticmethod
    def _host_identity() -> str:
        try:
            return f"{os.getuid()}:{os.getgid()}"
        except AttributeError:
            return ""


def create_execution_environment(request: EnvironmentRequest) -> ExecutionEnvironment:
    """Create exactly the Execution Environment requested by the composition layer."""
    validate_environment_request(request)
    target_repository = request.target_repository.resolve()
    if request.environment == "local":
        return LocalExecutionEnvironment(
            target_repository,
            maximum_output_characters=request.maximum_output_characters,
        )
    assert request.image is not None
    try:
        return DockerExecutionEnvironment(
            target_repository,
            image=request.image,
            maximum_output_characters=request.maximum_output_characters,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise EnvironmentCreationError(f"Unable to start Docker Environment: {error}") from error


def validate_environment_request(request: EnvironmentRequest) -> None:
    """Reject an invalid backend selection before any backend is started."""
    if request.environment not in {"local", "docker"}:
        raise ValueError(f"Unknown Execution Environment: {request.environment}. Choose local or docker.")
    if request.environment == "docker" and (not request.image or not request.image.strip()):
        raise ValueError("Docker Environment requires an image via --image.")
