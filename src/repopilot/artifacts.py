"""Per-run metadata and append-only trace persistence."""

from __future__ import annotations

import json
import os
import tempfile
import uuid
from pathlib import Path
from typing import Any


class RunArtifacts:
    """Keeps auditable Agent Run artifacts outside the Target Repository."""

    def __init__(self, state_directory: Path, *, secrets: list[str]):
        self.run_id = uuid.uuid4().hex
        self.path = state_directory.resolve() / self.run_id
        self.path.mkdir(parents=True, exist_ok=False)
        self._metadata_path = self.path / "metadata.json"
        self._trace_path = self.path / "trace.jsonl"
        self._secrets = tuple(secret for secret in secrets if len(secret) >= 4)

    @classmethod
    def reopen(cls, state_directory: Path, run_id: str, *, secrets: list[str]) -> RunArtifacts:
        """Open an existing Agent Run without allocating a new Run ID."""

        state_root = state_directory.resolve()
        path = (state_root / run_id).resolve()
        if path.parent != state_root:
            raise FileNotFoundError(f"No persisted Agent Run exists for {run_id}.")
        if not path.is_dir():
            raise FileNotFoundError(f"No persisted Agent Run exists for {run_id}.")
        artifacts = cls.__new__(cls)
        artifacts.run_id = run_id
        artifacts.path = path
        artifacts._metadata_path = path / "metadata.json"
        artifacts._trace_path = path / "trace.jsonl"
        artifacts._secrets = tuple(secret for secret in secrets if len(secret) >= 4)
        return artifacts

    def write_metadata(self, metadata: dict[str, Any]) -> None:
        self._metadata_path.write_text(json.dumps(self._redact(metadata), indent=2, sort_keys=True) + "\n")

    def write_text(self, filename: str, content: str) -> None:
        """Persist a named, redacted terminal Agent Run artifact."""
        (self.path / filename).write_text(self._redact(content))

    def write_json(self, filename: str, value: Any) -> None:
        """Persist a named, redacted JSON terminal Agent Run artifact."""
        (self.path / filename).write_text(json.dumps(self._redact(value), indent=2, sort_keys=True) + "\n")

    def append_trace(self, event_type: str, **data: Any) -> None:
        event = self._redact({"type": event_type, **data})
        with self._trace_path.open("a") as trace:
            trace.write(json.dumps(event, sort_keys=True) + "\n")

    def write_checkpoint(self, checkpoint: dict[str, Any]) -> None:
        """Atomically replace the resumable state for this Agent Run."""

        payload = json.dumps(self._redact(checkpoint), indent=2, sort_keys=True) + "\n"
        destination = self.path / "checkpoint.json"
        descriptor, temporary_name = tempfile.mkstemp(
            dir=destination.parent,
            prefix=".checkpoint-",
            suffix=".tmp",
            text=True,
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as temporary:
                temporary.write(payload)
                temporary.flush()
                os.fsync(temporary.fileno())
            os.replace(temporary_name, destination)
            directory_descriptor = os.open(destination.parent, os.O_RDONLY)
            try:
                os.fsync(directory_descriptor)
            finally:
                os.close(directory_descriptor)
        finally:
            temporary_path = Path(temporary_name)
            if temporary_path.exists():
                temporary_path.unlink()

    def read_checkpoint(self) -> dict[str, Any]:
        """Load the latest atomically persisted state for this Agent Run."""

        checkpoint_path = self.path / "checkpoint.json"
        if not checkpoint_path.is_file():
            raise FileNotFoundError(f"Agent Run {self.run_id} has no Checkpoint.")
        value = json.loads(checkpoint_path.read_text())
        if not isinstance(value, dict):
            raise ValueError(f"Agent Run {self.run_id} has an invalid Checkpoint.")
        return value

    def _redact(self, value: Any) -> Any:
        if isinstance(value, str):
            redacted = value
            for secret in self._secrets:
                redacted = redacted.replace(secret, "[REDACTED]")
            return redacted
        if isinstance(value, dict):
            return {key: self._redact(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self._redact(item) for item in value]
        return value
