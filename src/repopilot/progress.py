"""Bounded observations of completed native exploration; no inferred shell reads."""

from __future__ import annotations

import hashlib
import json
import posixpath

EXPLORATION_TOOLS = {"read_file", "search_code", "list_files"}


def observation_signature(name, arguments, observation):
    arguments = dict(arguments)
    if isinstance(arguments.get("path"), str):
        arguments["path"] = posixpath.normpath(arguments["path"])

    def stable(value):
        if isinstance(value, dict):
            return {key: stable(item) for key, item in value.items() if key != "duration_seconds"}
        if isinstance(value, list):
            return [stable(item) for item in value]
        return value

    # Full observations are passed here, before any model preview truncation.
    payload = json.dumps([name, arguments, stable(observation)], sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(payload.encode()).hexdigest()


class ProgressTracker:
    def __init__(self, *, enabled=True, window=12):
        self.enabled = enabled
        self.window = window
        self.history = []
        self.alerted = None
        self.last_verification = None

    def verification(self, observation):
        result = dict(observation.get("result", {}))
        for key in ("sequence", "reason", "scope", "supersedes", "explicit_check_id", "plan_step_ids", "check_id"):
            result.pop(key, None)
        signature = observation_signature("verify_task", {}, {"result": result})
        if signature != self.last_verification:
            self.reset()
        self.last_verification = signature

    def reset(self):
        self.history.clear()
        self.alerted = None

    def observe(self, call_id, name, arguments, observation):
        if name not in EXPLORATION_TOOLS or observation.get("ok") is not True:
            return None
        result = observation.get("result", {})
        if isinstance(result, dict) and result.get("exit_code", 0) != 0:
            return None
        signature = observation_signature(name, arguments, observation)
        repeated = any(item["signature"] == signature for item in self.history)
        if not repeated and (self.alerted or len({h["signature"] for h in self.history}) < len(self.history)):
            self.reset()
        item = {
            "signature": signature,
            "tool_call_id": call_id[:256],
            "tool_call_id_sha256": hashlib.sha256(call_id.encode()).hexdigest(),
            "tool_name": name,
            "arguments": {
                key: arguments[key][:512] if isinstance(arguments[key], str) else arguments[key]
                for key in ("path", "start_line", "max_lines", "max_results", "query", "offset")
                if key in arguments
            },
        }
        self.history = [*self.history, item][-self.window :]
        diagnostic = None
        for width in range(1, 5):
            if len(self.history) < width * 3:
                continue
            tail = self.history[-width * 3 :]
            signatures = [h["signature"] for h in tail]
            if signatures[:width] == signatures[width : 2 * width] == signatures[2 * width :]:
                unit = signatures[:width]
                canonical = min(unit[i:] + unit[:i] for i in range(width))
                cycle = hashlib.sha256(json.dumps(canonical).encode()).hexdigest()
                if self.enabled and self.alerted != cycle:
                    self.alerted = cycle
                    diagnostic = {"cycle_id": cycle, "width": width, "repetitions": 3, "calls": tail}
                break
        return {"repeated": repeated, "diagnostic": diagnostic, "signature": signature}

    def to_checkpoint(self):
        return {
            "enabled": self.enabled,
            "window": self.window,
            "history": self.history,
            "alerted": self.alerted,
            "last_verification": self.last_verification,
        }

    @classmethod
    def from_checkpoint(cls, value):
        if not isinstance(value, dict) or type(value.get("enabled", True)) is not bool:
            raise ValueError("Checkpoint has invalid ProgressTracker configuration.")
        if value.get("window", 12) != 12:
            raise ValueError("Unsupported ProgressTracker window.")
        history = value.get("history", [])
        if (
            not isinstance(history, list)
            or len(history) > 12
            or any(
                not isinstance(h, dict)
                or not isinstance(h.get("signature"), str)
                or not isinstance(h.get("tool_call_id"), str)
                or h.get("tool_name") not in EXPLORATION_TOOLS
                or not isinstance(h.get("arguments"), dict)
                for h in history
            )
        ):
            raise ValueError("Checkpoint has invalid ProgressTracker history.")
        tracker = cls(enabled=value.get("enabled", True))
        tracker.history = list(history)
        tracker.alerted = value.get("alerted")
        tracker.last_verification = value.get("last_verification")
        if tracker.alerted is not None and not isinstance(tracker.alerted, str):
            raise ValueError("Checkpoint has invalid ProgressTracker cycle.")
        return tracker


def repeated_exploration(events):
    tracker = ProgressTracker(enabled=False)
    calls = {}
    count = 0
    completed = 0
    for event in events:
        kind = event.get("type")
        if kind in {"source_changed", "repository_changed"}:
            tracker.reset()
        elif kind == "tool_call":
            calls[event.get("tool_call_id")] = event
        elif kind == "tool_result":
            call = calls.pop(event.get("tool_call_id"), None)
            if call and call.get("tool_name") == "verify_task" and event.get("observation", {}).get("ok"):
                tracker.verification(event["observation"])
            if call:
                observed = tracker.observe(
                    call["tool_call_id"], call.get("tool_name"), call.get("arguments", {}), event.get("observation", {})
                )
                if observed:
                    completed += 1
                    count += observed["repeated"]
    return count if completed else None
