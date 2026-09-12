"""Bounded receipts from completed tool calls, without model-written summaries."""

from __future__ import annotations

import json
import re


def byte_size(value) -> int:
    return len(json.dumps(value, ensure_ascii=False).encode())


def excerpt(value: str, limit: int) -> str:
    raw = value.encode()
    return value if len(raw) <= limit else raw[:limit].decode(errors="ignore") + "…"


def _object(text):
    try:
        value = json.loads(text)
    except (ValueError, TypeError):
        return {}
    return value if isinstance(value, dict) else {}


def progress_memory(messages, max_bytes=8192):
    """Rebuild from retained history; repeat reads/checks replace, never inflate receipts."""
    calls = {}
    checks = {}
    reads = {}
    actions = {}
    for index, message in enumerate(messages):
        for call in message.get("tool_calls", []):
            calls[call["id"]] = call.get("function", {})
        if message.get("role") != "tool":
            continue
        call_id = message.get("tool_call_id")
        call = calls.pop(call_id, None)
        if call is None:
            continue
        name = call.get("name")
        args = _object(call.get("arguments"))
        observation = _object(message.get("content"))
        result = observation.get("result", {})
        result = result if isinstance(result, dict) else {}
        command = result.get("result", result)
        command = command if isinstance(command, dict) else {}
        receipt = {"tool": name, "tool_call_id": excerpt(str(call_id), 128), "history_index": index}
        if "ok" in observation:
            receipt["ok"] = observation["ok"]
        if "exit_code" in command:
            receipt["exit_code"] = command["exit_code"]
        if observation.get("artifact"):
            receipt["artifact"] = excerpt(json.dumps(observation["artifact"]), 320)
        if name == "verify_task":
            text = str(args.get("command", ""))
            receipt["command"] = excerpt(str(text), 512)
            receipt["check_id"] = excerpt(str(args.get("check_id", "")), 128)
            pair = checks.pop(text, [receipt, receipt])
            pair[1] = receipt
            checks[text] = pair
        elif name == "read_file" and args.get("path"):
            path = str(args["path"])
            receipt.update(path=excerpt(path, 256), start_line=args.get("start_line", 1))
            text = result.get("stdout", "")
            if isinstance(text, str):
                receipt["excerpt"] = excerpt(text, 640 if path.endswith(".md") else 384)
            key = (path, str(args.get("start_line", 1)))
            reads.pop(key, None)
            reads[key] = receipt
        elif name in {"apply_patch", "run_command", "git_commit", "update_plan", "replan"}:
            # Do not interpret a failed or merely requested action as a completed change.
            if "applied" in result:
                receipt["applied"] = result["applied"]
            if name == "apply_patch":
                paths = re.findall(
                    r"^(?:\*\*\* (?:Update|Add|Delete) File: |\+\+\+ b/)(.+)$", str(args.get("patch", "")), re.MULTILINE
                )
                receipt["paths"] = [excerpt(path, 256) for path in dict.fromkeys(paths)][:8]
            if args.get("command"):
                receipt["command"] = excerpt(str(args["command"]), 320)
            if args.get("step_id"):
                receipt.update(step_id=excerpt(str(args["step_id"]), 128), status=args.get("status"))
            actions.pop(name, None)
            actions[name] = receipt
    entries = []
    # Keep the first and latest execution of each recently used verification command.
    for first, last in list(checks.values())[-8:]:
        entries.extend([dict(first, occurrence="first")])
        if first != last:
            entries.append(dict(last, occurrence="latest"))
    entries.extend(reversed(list(actions.values())))
    recent_reads = list(reversed(list(reads.values())))
    entries.extend(r for r in recent_reads if r["path"].endswith(".md"))
    entries.extend(r for r in recent_reads if not r["path"].endswith(".md"))
    memory = {"historical_tool_receipts": [], "omitted_receipts": 0}
    for entry in entries:
        memory["historical_tool_receipts"].append(entry)
        if byte_size(memory) > max_bytes:
            memory["historical_tool_receipts"].pop()
            memory["omitted_receipts"] += 1
    # The omitted count can gain digits after an entry was accepted.
    while memory["historical_tool_receipts"] and byte_size(memory) > max_bytes:
        memory["historical_tool_receipts"].pop()
        memory["omitted_receipts"] += 1
    return memory


def compact_observation(message, preview_bytes):
    """Shorten payloads while preserving result status and trace provenance."""
    raw = message.get("content", "")
    if not isinstance(raw, str) or len(raw.encode()) <= preview_bytes:
        return message
    observation = _object(raw)
    result = observation.get("result", {})
    result = result if isinstance(result, dict) else {}
    command = result.get("result", result)
    command = command if isinstance(command, dict) else {}
    compact = {"truncated": True, "trace_tool_call_id": message.get("tool_call_id")}
    for key in ["ok", "error", "artifact", "exit_code", "applied"]:
        if key in observation:
            compact[key] = observation[key]
    if "exit_code" in command:
        compact["exit_code"] = command["exit_code"]
    if "applied" in result:
        compact["applied"] = result["applied"]
    # Prefer the actual output to an arbitrary prefix of its serialized envelope.
    payload = command.get("stdout") or command.get("stderr") or observation.get("preview") or raw
    compact["preview"] = excerpt(str(payload), preview_bytes)
    return {**message, "content": json.dumps(compact, ensure_ascii=False)}
