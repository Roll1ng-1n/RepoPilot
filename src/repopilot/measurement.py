"""Explicit nested time intervals and conservative source-change evidence."""

from __future__ import annotations

import hashlib
import subprocess
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

SOURCE_SUFFIXES = {".py", ".pyi", ".js", ".jsx", ".ts", ".tsx", ".go", ".rs", ".c", ".h", ".cpp", ".java", ".sh"}


class TimeRecorder:
    """Partition explicitly observed active intervals, including nested summaries.

    Parent exclusive time stops while a child runs. No wall-clock remainder is
    inferred for old traces or an unfinished session.
    """

    def __init__(self, artifacts, *, clock=time.monotonic):
        self.artifacts = artifacts
        self.clock = clock
        self.stack = []
        self.step = None
        self.request = None

    @contextmanager
    def measure(self, operation, *, category="orchestration", tool_call_id=None):
        span_id = uuid.uuid4().hex
        started = self.clock()
        frame = {"children": 0.0}
        self.stack.append(frame)
        self.artifacts.append_trace(
            "operation_started",
            span_id=span_id,
            operation=operation,
            run_id=self.artifacts.run_id,
            step=self.step,
            request=self.request,
            tool_call_id=tool_call_id,
            category=category,
            utc=datetime.now(timezone.utc).isoformat(),
        )
        outcome = "completed"
        try:
            yield
        except BaseException:
            outcome = "interrupted"
            raise
        finally:
            elapsed = self.clock() - started
            self.stack.pop()
            if self.stack:
                self.stack[-1]["children"] += elapsed
            self.artifacts.append_trace(
                "operation_finished",
                span_id=span_id,
                operation=operation,
                run_id=self.artifacts.run_id,
                step=self.step,
                request=self.request,
                tool_call_id=tool_call_id,
                category=category,
                outcome=outcome,
                duration_seconds=elapsed,
                exclusive_seconds=max(0.0, elapsed - frame["children"]),
                utc=datetime.now(timezone.utc).isoformat(),
            )


def source_state(root: Path) -> dict[str, str]:
    """Hash Git-visible source bytes; test caches and ignored files are excluded."""
    result = subprocess.run(
        ["git", "-C", str(root), "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        capture_output=True,
        check=False,
    )
    paths = (
        [root / name.decode(errors="surrogateescape") for name in result.stdout.split(b"\0") if name]
        if result.returncode == 0
        else list(root.rglob("*"))
    )
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(set(paths))
        if path.is_file()
        and not path.is_symlink()
        and path.suffix in SOURCE_SUFFIXES
        and not {".git", "__pycache__", ".pytest_cache", ".ruff_cache"}.intersection(path.parts)
    }


def timing_metrics(events: list[dict]) -> dict:
    starts = {e.get("span_id"): e for e in events if e.get("type") == "operation_started"}
    finishes = [e for e in events if e.get("type") == "operation_finished"]
    sessions = [e for e in finishes if e.get("operation") == "active_run"]
    complete = bool(sessions) and all(any(f.get("span_id") == key for f in finishes) for key in starts)
    declared_sessions = sum(e.get("type") in {"run_started", "run_resumed"} for e in events)
    if declared_sessions > len(sessions):
        complete = False
    totals = {
        category: sum(e.get("exclusive_seconds", 0) for e in finishes if e.get("category") == category)
        if starts
        else None
        for category in ("model", "tool", "orchestration")
    }
    idle = 0.0
    previous = None
    for event in events:
        if event.get("operation") != "active_run":
            continue
        if event["type"] == "operation_started" and previous is not None and event.get("utc"):
            idle += max(0.0, (datetime.fromisoformat(event["utc"]) - previous).total_seconds())
        if event["type"] == "operation_finished" and event.get("utc"):
            previous = datetime.fromisoformat(event["utc"])
    return {
        "coverage": "complete" if complete else "partial" if starts else "unavailable",
        "active_seconds": sum(e["duration_seconds"] for e in sessions) if complete else None,
        "idle_seconds": idle if complete else None,
        "tool_seconds": totals["tool"],
        "orchestration_seconds": totals["orchestration"] if complete else None,
        "measured_orchestration_seconds": totals["orchestration"],
        "operations": {
            name: sum(e["duration_seconds"] for e in finishes if e.get("operation") == name)
            for name in sorted({e["operation"] for e in finishes})
        },
    }
