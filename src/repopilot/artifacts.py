"""Per-run metadata and append-only trace persistence."""

from __future__ import annotations

import json
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
