"""Execution-environment port and its local implementation."""

from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class Command:
    """A command requested by a Repository Tool."""

    argv: tuple[str, ...]
    timeout_seconds: float = 30.0


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


class LocalExecutionEnvironment:
    """Runs commands directly in one target repository."""

    def __init__(self, target_repository: Path, *, maximum_output_characters: int = 20_000):
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
            stdout, stdout_truncated = self._truncate(self._as_text(error.stdout))
            stderr, stderr_truncated = self._truncate(self._as_text(error.stderr))
            return CommandResult(
                exit_code=-1,
                stdout=stdout,
                stderr=stderr or f"Command timed out after {command.timeout_seconds} seconds.",
                duration_seconds=time.monotonic() - started_at,
                truncated=True or stdout_truncated or stderr_truncated,
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
