import json

from repopilot.context import ContextManager, ContextStrategy, ContextSummary, model_summary_generator
from repopilot.model import AssistantTurn


def _context_summary(messages: list[dict]) -> dict:
    for message in messages:
        content = message.get("content")
        if not isinstance(content, str):
            continue
        try:
            value = json.loads(content)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict) and isinstance(value.get("context_summary"), dict):
            return value["context_summary"]
    raise AssertionError("No structured Context summary reached the model.")


def test_sliding_window_keeps_anchors_facts_and_one_complete_recent_agent_step() -> None:
    context = ContextManager(ContextStrategy.SLIDING_WINDOW, max_characters=430)
    context.record_fact("README.md is the requested file.")
    messages = [
        {"role": "system", "content": "Follow the Agent Run protocol. Current Plan: {}"},
        {"role": "user", "content": "Update the README."},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "old-call",
                    "type": "function",
                    "function": {"name": "read_file", "arguments": '{"path": "old.md"}'},
                }
            ],
        },
        {"role": "tool", "tool_call_id": "old-call", "content": json.dumps({"ok": True, "result": "old"})},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "recent-read",
                    "type": "function",
                    "function": {"name": "read_file", "arguments": '{"path": "README.md"}'},
                },
                {
                    "id": "recent-diff",
                    "type": "function",
                    "function": {"name": "view_diff", "arguments": "{}"},
                },
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "recent-read",
            "content": json.dumps({"ok": True, "result": "README contents"}),
        },
        {
            "role": "tool",
            "tool_call_id": "recent-diff",
            "content": json.dumps({"ok": True, "result": "no diff"}),
        },
    ]

    selected = context.for_model(
        messages,
        {"version": 2, "reason": "Inspection completed.", "steps": []},
    )

    assert selected[0]["role"] == "system"
    assert '"version": 2' in selected[0]["content"]
    assert selected[1] == messages[1]
    assert any("README.md is the requested file." in str(message["content"]) for message in selected)
    assert all(message.get("tool_call_id") != "old-call" for message in selected)
    assert any(message.get("tool_call_id") == "recent-read" for message in selected)
    assert any(message.get("tool_call_id") == "recent-diff" for message in selected)
    recent_assistant = next(message for message in selected if message.get("role") == "assistant")
    assert [call["id"] for call in recent_assistant["tool_calls"]] == ["recent-read", "recent-diff"]


def test_summary_strategy_compresses_old_steps_into_the_required_structured_fields() -> None:
    def summarize(_previous: ContextSummary | None, _steps: list[list[dict]]) -> ContextSummary:
        return ContextSummary(
            important_facts=[],
            completed_work=["Inspected the existing README."],
            decisions=["Update the README directly."],
            open_questions=["Which verification command should run?"],
        )

    context = ContextManager(ContextStrategy.SUMMARY, max_characters=500, summarizer=summarize)
    context.record_fact("The requested change is limited to README.md.")
    messages = [
        {"role": "system", "content": "Follow the Agent Run protocol. Current Plan: {}"},
        {"role": "user", "content": "Update the README."},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "old-call",
                    "type": "function",
                    "function": {"name": "read_file", "arguments": '{"path": "README.md"}'},
                }
            ],
        },
        {"role": "tool", "tool_call_id": "old-call", "content": "x" * 800},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "recent-call",
                    "type": "function",
                    "function": {"name": "view_diff", "arguments": "{}"},
                }
            ],
        },
        {"role": "tool", "tool_call_id": "recent-call", "content": json.dumps({"ok": True})},
    ]

    selected = context.for_model(messages, {"version": 1, "reason": "Initial", "steps": []})

    assert _context_summary(selected) == {
        "completed_work": ["Inspected the existing README."],
        "decisions": ["Update the README directly."],
        "important_facts": ["The requested change is limited to README.md."],
        "open_questions": ["Which verification command should run?"],
    }
    assert all(message.get("tool_call_id") != "old-call" for message in selected)
    assert any(message.get("tool_call_id") == "recent-call" for message in selected)


def test_model_summary_generator_requests_and_validates_a_structured_summary() -> None:
    class SummaryModel:
        model_name = "summary-model"

        def __init__(self) -> None:
            self.requests: list[tuple[list[dict], list[dict]]] = []

        def complete(self, messages: list[dict], tools: list[dict]) -> AssistantTurn:
            self.requests.append((messages, tools))
            return AssistantTurn(
                content=json.dumps(
                    {
                        "important_facts": ["The README exists."],
                        "completed_work": ["Inspected the README."],
                        "decisions": ["Edit only the README."],
                        "open_questions": [],
                    }
                )
            )

    model = SummaryModel()

    summary = model_summary_generator(model)(None, [[{"role": "assistant", "content": "Inspected README."}]])

    assert summary == ContextSummary(
        important_facts=["The README exists."],
        completed_work=["Inspected the README."],
        decisions=["Edit only the README."],
        open_questions=[],
    )
    assert model.requests[0][1] == []
    assert json.loads(model.requests[0][0][1]["content"])["older_agent_steps"] == [
        [{"role": "assistant", "content": "Inspected README."}]
    ]


def test_summary_failure_falls_back_to_sliding_window_and_restores_that_state() -> None:
    def broken_summary(_previous: ContextSummary | None, _steps: list[list[dict]]) -> ContextSummary:
        raise TimeoutError("summary provider timed out")

    context = ContextManager(ContextStrategy.SUMMARY, max_characters=250, summarizer=broken_summary)
    messages = [
        {"role": "system", "content": "Follow the Agent Run protocol. Current Plan: {}"},
        {"role": "user", "content": "Update the README."},
        {"role": "assistant", "content": None, "tool_calls": []},
        {"role": "user", "content": "x" * 500},
        {"role": "assistant", "content": None, "tool_calls": []},
        {"role": "user", "content": "Recent Tool Call result."},
    ]

    selection = context.prepare(messages, {"version": 1, "reason": "Initial", "steps": []})
    restored = ContextManager.from_checkpoint(context.to_checkpoint(), summarizer=broken_summary)

    assert selection.events == [{"type": "context_summary_fallback", "reason": "summary provider timed out"}]
    assert all(message["content"] != "x" * 500 for message in selection.messages)
    assert restored.to_checkpoint()["fallback"] == {"active": True, "reason": "summary provider timed out"}


def test_summary_strategy_keeps_facts_recorded_after_an_older_step_was_summarized() -> None:
    context = ContextManager(
        ContextStrategy.SUMMARY,
        max_characters=250,
        summarizer=lambda _previous, _steps: ContextSummary([], ["Completed inspection."], [], []),
    )
    messages = [
        {"role": "system", "content": "Follow the Agent Run protocol. Current Plan: {}"},
        {"role": "user", "content": "Update the README."},
        {"role": "assistant", "content": None, "tool_calls": []},
        {"role": "tool", "tool_call_id": "old", "content": "x" * 500},
        {"role": "assistant", "content": None, "tool_calls": []},
        {"role": "tool", "tool_call_id": "recent", "content": "recent"},
    ]

    context.for_model(messages, {"version": 1, "reason": "Initial", "steps": []})
    context.record_fact("A verification command is still required.")
    selected = context.for_model(messages, {"version": 1, "reason": "Initial", "steps": []})

    assert any("A verification command is still required." in str(message["content"]) for message in selected)
    assert context.to_checkpoint()["summary"]["important_facts"] == ["A verification command is still required."]
