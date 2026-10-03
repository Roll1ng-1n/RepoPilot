"""The context selector and request executor must agree at the size boundary."""

import json

from repopilot.context import ContextManager


def test_bound_request_accounts_for_complete_envelope():
    messages = [
        {"role": "system", "content": "Preserve instructions"},
        {"role": "user", "content": "Repair and finish"},
        {"role": "assistant", "tool_calls": [{"id": "old", "function": {"name": "read_file"}}]},
        {"role": "tool", "tool_call_id": "old", "content": "x" * 500},
        {"role": "assistant", "content": "Latest completed observation"},
    ]
    schemas = [{"description": "ASCII and 中文"}]
    size = len(json.dumps({"messages": messages, "tools": schemas}, ensure_ascii=False).encode())
    context = ContextManager()
    context.context_window_tokens = size + context.output_reserve_tokens + 1024 - 1
    bounded = context.bound_request(messages, schemas)
    envelope = len(json.dumps({"messages": bounded, "tools": schemas}, ensure_ascii=False).encode())
    assert envelope + context.output_reserve_tokens + 1024 <= context.context_window_tokens
    assert bounded[:2] == messages[:2]
    assert bounded[-1] == messages[-1]
