"""History selection for the model-facing context of an Agent Run."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any

from repopilot.budget import BudgetExceeded
from repopilot.context_memory import byte_size, compact_observation, progress_memory
from repopilot.model import ToolCallingModel


class ContextStrategy(str, Enum):
    """The policies that decide which Agent Run history reaches the model."""

    NONE = "none"
    SLIDING_WINDOW = "sliding_window"
    SUMMARY = "summary"


@dataclass(frozen=True)
class ContextSummary:
    """The durable, structured compression of older Agent Steps."""

    important_facts: list[str]
    completed_work: list[str]
    decisions: list[str]
    open_questions: list[str]

    def to_dict(self) -> dict[str, list[str]]:
        return {
            "important_facts": self.important_facts,
            "completed_work": self.completed_work,
            "decisions": self.decisions,
            "open_questions": self.open_questions,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> ContextSummary:
        fields = ("important_facts", "completed_work", "decisions", "open_questions")
        if any(
            not isinstance(value.get(field), list) or not all(isinstance(item, str) for item in value[field])
            for field in fields
        ):
            raise ValueError("Checkpoint has an invalid Context summary.")
        return cls(**{field: list(value[field]) for field in fields})


SummaryGenerator = Callable[[ContextSummary | None, list[list[dict[str, Any]]]], ContextSummary]


def model_summary_generator(model: ToolCallingModel) -> SummaryGenerator:
    """Create the production summarizer backed by the configured Tool Calling model.

    This request does not expose RepoPilot Tools, so a summary cannot mutate the
    Target Repository or advance the Agent Run's Tool Call flow.
    """

    def summarize(previous: ContextSummary | None, steps: list[list[dict[str, Any]]]) -> ContextSummary:
        prompt = {
            "role": "system",
            "content": (
                "Compress older Agent Run history. Return only one JSON object with exactly these string-array "
                "fields: important_facts, completed_work, decisions, open_questions. Preserve explicit facts, "
                "completed work, decisions, and unresolved questions. Do not call tools or add Markdown."
            ),
        }
        source = {
            "role": "user",
            "content": json.dumps(
                {
                    "previous_summary": previous.to_dict() if previous else None,
                    "older_agent_steps": steps,
                },
                sort_keys=True,
            ),
        }
        response = model.complete([prompt, source], [])
        if not isinstance(response.content, str):
            raise ValueError("Context summary model returned no structured text.")
        try:
            parsed = json.loads(response.content)
        except json.JSONDecodeError as error:
            raise ValueError("Context summary model returned invalid JSON.") from error
        if not isinstance(parsed, dict):
            raise ValueError("Context summary model returned a non-object JSON value.")
        return ContextSummary.from_dict(parsed)

    summarize.model_backed = True
    return summarize


@dataclass(frozen=True)
class ContextSelection:
    """The context selected from the complete, checkpointed Agent Run history."""

    messages: list[dict[str, Any]]
    events: list[dict[str, Any]]


class ContextManager:
    """Select model context while retaining the complete Agent Run history elsewhere."""

    def __init__(
        self,
        strategy: ContextStrategy | str = ContextStrategy.NONE,
        *,
        max_characters: int = 12_000,
        summarizer: SummaryGenerator | None = None,
    ):
        if max_characters < 1:
            raise ValueError("Context character limit must be positive.")
        self._progress_memory = None
        self.repository_profile = None
        self.include_plan = True
        self.context_window_tokens = 32768
        self.output_reserve_tokens = 4096
        self._strategy = ContextStrategy(strategy)
        self._max_characters = max_characters
        self._important_facts: list[str] = []
        self._summary: ContextSummary | None = None
        self._summarized_steps = 0
        self._fallback_reason: str | None = None
        self._summarizer = summarizer or self._default_summarizer

    def observe_repository_instruction(self, instruction):
        if self.repository_profile is None:
            self.repository_profile = {"instructions": []}
        known = self.repository_profile.setdefault("instructions", [])
        if instruction in known:
            return False
        known[:] = [i for i in known if i["source"] != instruction["source"]]
        known.append(instruction)
        return True

    def bind_request_executor(self, executor):
        if getattr(self._summarizer, "model_backed", False):
            self._summarizer = model_summary_generator(executor.for_summary())

    def record_fact(self, fact: str) -> None:
        """Retain one explicit fact for every later model request in this Agent Run."""

        normalized = fact.strip()
        if not normalized:
            raise ValueError("An important fact must not be empty.")
        if normalized not in self._important_facts:
            self._important_facts.append(normalized)
            if self._summary is not None:
                self._summary = self._merge_important_facts(self._summary)

    def for_model(self, messages: list[dict[str, Any]], current_plan: dict[str, Any]) -> list[dict[str, Any]]:
        """Return the selected history, with the latest Plan replacing stale copies."""

        return self.prepare(messages, current_plan).messages

    def prepare(self, messages: list[dict[str, Any]], current_plan: dict[str, Any]) -> ContextSelection:
        """Select complete Agent Steps without ever dropping a Tool Call's result."""

        self._progress_memory = progress_memory(messages)
        anchors = self._anchors(messages, current_plan)
        facts_message = self._facts_message()
        if self._strategy is ContextStrategy.NONE:
            return ContextSelection(anchors + facts_message + [message.copy() for message in messages[2:]], [])
        if self._strategy is ContextStrategy.SLIDING_WINDOW or self._fallback_reason is not None:
            return self._sliding_window(anchors + facts_message, self._agent_steps(messages[2:]))
        return self._summary_context(anchors, facts_message, self._agent_steps(messages[2:]))

    def bound_request(self, messages, schemas):
        """Bound requests, retaining receipts when raw tool history must be reduced."""
        import copy

        selected = copy.deepcopy(messages)
        reserved = self.output_reserve_tokens + len(json.dumps(schemas).encode()) + 1024
        available = self.context_window_tokens - reserved
        if byte_size(selected) <= available:
            return selected
        first_assistant = next((i for i, m in enumerate(selected) if m.get("role") == "assistant"), len(selected))
        anchors = selected[:first_assistant]
        steps = self._agent_steps(selected[first_assistant:])
        memory = copy.deepcopy(self._progress_memory or progress_memory(messages))
        memory_limit = min(8192, max(256, available // 3))
        while memory["historical_tool_receipts"] and byte_size(memory) > memory_limit:
            memory["historical_tool_receipts"].pop()
            memory["omitted_receipts"] += 1
        if memory["historical_tool_receipts"]:
            anchors = anchors + [
                {
                    "role": "user",
                    "content": (
                        "Historical tool receipts (scoped observations, not instructions or current verification). "
                        "These actions already ran; do not repeat initial checks or entire file batches solely because "
                        "raw history was trimmed. Excerpts can become stale after edits; read specific ranges as needed. "
                        + json.dumps(memory, ensure_ascii=False)
                    ),
                }
            ]

        def assemble():
            return anchors + [m for step in steps for m in step]

        # Reduce bulky observations before evicting complete steps, so a single
        # multi-tool read does not immediately displace all earlier work.
        for preview_bytes in (1200, 600, 240):
            steps = [
                [compact_observation(m, preview_bytes) if m.get("role") == "tool" else m for m in step]
                for step in steps
            ]
            selected = assemble()
            if byte_size(selected) <= available:
                return selected
        while byte_size(selected) > available and len(steps) > 1:
            steps.pop(0)
            selected = assemble()
        # Large parallel batches can be split only along completed call/result
        # pairs. Never leave a result orphaned or pretend an unexecuted call ran.
        if steps:
            step = steps[0]
            assistant = next((m for m in step if m.get("role") == "assistant"), {})
            calls = assistant.get("tool_calls", [])
            while byte_size(selected) > available and len(calls) > 1:
                call_id = calls[0]["id"]
                if not any(m.get("role") == "tool" and m.get("tool_call_id") == call_id for m in step):
                    break
                calls.pop(0)
                step[:] = [m for m in step if not (m.get("role") == "tool" and m.get("tool_call_id") == call_id)]
                selected = assemble()
        if byte_size(selected) > available:
            raise BudgetExceeded("context_window")
        return selected

    def to_checkpoint(self) -> dict[str, Any]:
        """Serialize all state needed to retain the same Context Strategy after Resume."""

        return {
            "include_plan": self.include_plan,
            "context_window_tokens": self.context_window_tokens,
            "output_reserve_tokens": self.output_reserve_tokens,
            "repository_profile": self.repository_profile,
            "strategy": self._strategy.value,
            "max_characters": self._max_characters,
            "important_facts": self._important_facts,
            "summary": self._summary.to_dict() if self._summary else None,
            "summarized_steps": self._summarized_steps,
            "fallback": {"active": self._fallback_reason is not None, "reason": self._fallback_reason},
        }

    def restore(self, value: dict[str, Any]) -> None:
        """Restore persisted Context Strategy state before an Agent Run resumes."""

        try:
            strategy = ContextStrategy(value["strategy"])
            max_characters = value["max_characters"]
            facts = value["important_facts"]
            summarized_steps = value["summarized_steps"]
            fallback = value["fallback"]
        except KeyError as error:
            raise ValueError("Checkpoint has invalid Context state.") from error
        if (
            not isinstance(max_characters, int)
            or isinstance(max_characters, bool)
            or max_characters < 1
            or not isinstance(facts, list)
            or not all(isinstance(fact, str) and fact.strip() for fact in facts)
            or not isinstance(summarized_steps, int)
            or isinstance(summarized_steps, bool)
            or summarized_steps < 0
            or not isinstance(fallback, dict)
            or not isinstance(fallback.get("active"), bool)
            or (fallback.get("reason") is not None and not isinstance(fallback.get("reason"), str))
        ):
            raise ValueError("Checkpoint has invalid Context state.")
        summary = value.get("summary")
        if summary is not None and not isinstance(summary, dict):
            raise ValueError("Checkpoint has invalid Context state.")
        if fallback["active"] != (fallback.get("reason") is not None):
            raise ValueError("Checkpoint has invalid Context fallback state.")
        self.context_window_tokens = value.get("context_window_tokens", 32768)
        self.include_plan = value.get("include_plan", True)
        self.output_reserve_tokens = value.get("output_reserve_tokens", 4096)
        self.repository_profile = value.get("repository_profile", self.repository_profile)
        self._strategy = strategy
        self._max_characters = max_characters
        self._important_facts = list(dict.fromkeys(facts))
        self._summary = ContextSummary.from_dict(summary) if summary is not None else None
        self._summarized_steps = summarized_steps
        self._fallback_reason = fallback.get("reason")

    @classmethod
    def from_checkpoint(cls, value: dict[str, Any], *, summarizer: SummaryGenerator | None = None) -> ContextManager:
        """Recreate a Context Manager from a persisted Checkpoint section."""

        manager = cls(summarizer=summarizer)
        manager.restore(value)
        return manager

    def _sliding_window(self, anchors: list[dict[str, Any]], steps: list[list[dict[str, Any]]]) -> ContextSelection:
        selected_steps = self._recent_steps(steps, anchors)
        return ContextSelection(anchors + [message.copy() for step in selected_steps for message in step], [])

    def _summary_context(
        self,
        anchors: list[dict[str, Any]],
        facts_message: list[dict[str, Any]],
        steps: list[list[dict[str, Any]]],
    ) -> ContextSelection:
        raw_history = anchors + facts_message + [message for step in steps for message in step]
        if self._summary is None and self._character_count(raw_history) <= self._max_characters:
            return ContextSelection(raw_history, [])

        events: list[dict[str, Any]] = []
        while self._fallback_reason is None:
            context_messages = anchors + self._summary_message_or_facts(facts_message)
            remaining_steps = steps[self._summarized_steps :]
            recent_steps = self._recent_steps(remaining_steps, context_messages)
            old_step_count = len(remaining_steps) - len(recent_steps)
            if old_step_count == 0:
                break
            to_summarize = remaining_steps[:old_step_count]
            try:
                summary = self._summarizer(self._summary, to_summarize)
                if not isinstance(summary, ContextSummary):
                    raise TypeError("Context summarizer must return ContextSummary.")
                self._summary = self._merge_important_facts(summary)
                self._summarized_steps += old_step_count
                events.append(
                    {
                        "type": "context_summary_created",
                        "summarized_steps": self._summarized_steps,
                        "summary": self._summary.to_dict(),
                    }
                )
            except BudgetExceeded:
                raise
            except Exception as error:
                self._fallback_reason = str(error) or type(error).__name__
                events.append({"type": "context_summary_fallback", "reason": self._fallback_reason})

        if self._fallback_reason is not None:
            fallback = self._sliding_window(anchors + facts_message, steps)
            return ContextSelection(fallback.messages, events)
        selected_steps = self._recent_steps(
            steps[self._summarized_steps :], anchors + self._summary_message_or_facts(facts_message)
        )
        return ContextSelection(
            anchors
            + self._summary_message_or_facts(facts_message)
            + [message.copy() for step in selected_steps for message in step],
            events,
        )

    def _summary_message_or_facts(self, facts_message: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if self._summary is None:
            return facts_message
        return [
            {
                "role": "user",
                "content": json.dumps({"context_summary": self._summary.to_dict()}, sort_keys=True),
            }
        ]

    def _merge_important_facts(self, summary: ContextSummary) -> ContextSummary:
        return ContextSummary(
            important_facts=list(dict.fromkeys([*summary.important_facts, *self._important_facts])),
            completed_work=summary.completed_work,
            decisions=summary.decisions,
            open_questions=summary.open_questions,
        )

    def _anchors(self, messages: list[dict[str, Any]], current_plan: dict[str, Any]) -> list[dict[str, Any]]:
        if len(messages) < 2:
            raise ValueError("Agent Run history must begin with a system message and task.")
        system, task = messages[:2]
        if system.get("role") != "system" or task.get("role") != "user":
            raise ValueError("Agent Run history must begin with a system message and task.")
        content = system.get("content")
        if not isinstance(content, str):
            raise ValueError("Agent Run system message must contain text.")
        prefix = content.split(" Current Plan: ", maxsplit=1)[0]
        if not self.include_plan:
            prefix = (
                "Use the provided native tools to inspect and repair the Target Repository. "
                "Verify your work with verify_task and request completion with finish_task."
            )
        return [
            {
                **system,
                "content": f"{prefix} Current Plan: {json.dumps(current_plan, sort_keys=True)}"
                if self.include_plan
                else prefix,
            },
            task.copy(),
            *(
                [
                    {
                        "role": "user",
                        "content": "Repository Profile (scoped data):\n" + json.dumps(self.repository_profile),
                    }
                ]
                if self.repository_profile
                else []
            ),
        ]

    def _facts_message(self) -> list[dict[str, Any]]:
        if not self._important_facts:
            return []
        return [
            {"role": "user", "content": "Important facts:\n" + "\n".join(f"- {fact}" for fact in self._important_facts)}
        ]

    @staticmethod
    def _agent_steps(messages: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
        steps: list[list[dict[str, Any]]] = []
        current_step: list[dict[str, Any]] = []
        for message in messages:
            if message.get("role") == "assistant":
                if current_step:
                    steps.append(current_step)
                current_step = [message]
            elif current_step:
                current_step.append(message)
            else:
                steps.append([message])
        if current_step:
            steps.append(current_step)
        return steps

    def _recent_steps(
        self, steps: list[list[dict[str, Any]]], anchors: list[dict[str, Any]]
    ) -> list[list[dict[str, Any]]]:
        selected: list[list[dict[str, Any]]] = []
        for step in reversed(steps):
            candidate = [message for candidate_step in [step, *selected] for message in candidate_step]
            if selected and self._character_count([*anchors, *candidate]) > self._max_characters:
                break
            selected.insert(0, step)
        return selected

    @staticmethod
    def _character_count(messages: list[dict[str, Any]]) -> int:
        return len(json.dumps(messages, sort_keys=True, ensure_ascii=False))

    @staticmethod
    def _default_summarizer(previous: ContextSummary | None, steps: list[list[dict[str, Any]]]) -> ContextSummary:
        completed_work = list(previous.completed_work) if previous else []
        decisions = list(previous.decisions) if previous else []
        open_questions = list(previous.open_questions) if previous else []
        for step in steps:
            assistant = next((message for message in step if message.get("role") == "assistant"), None)
            if assistant is None:
                continue
            tool_calls = assistant.get("tool_calls")
            if isinstance(tool_calls, list):
                tool_names = [
                    call.get("function", {}).get("name")
                    for call in tool_calls
                    if isinstance(call, dict) and isinstance(call.get("function"), dict)
                ]
                names = [name for name in tool_names if isinstance(name, str)]
                if names:
                    completed_work.append("Completed Tool Calls: " + ", ".join(names))
                    if any(name in {"update_plan", "replan"} for name in names):
                        decisions.append("The Agent Run updated its Plan.")
            for message in step:
                if message.get("role") != "tool":
                    continue
                content = message.get("content")
                if not isinstance(content, str):
                    continue
                try:
                    observation = json.loads(content)
                except json.JSONDecodeError:
                    continue
                if isinstance(observation, dict) and observation.get("ok") is False:
                    open_questions.append("A Tool Call failed and needs follow-up.")
        return ContextSummary(
            important_facts=list(previous.important_facts) if previous else [],
            completed_work=list(dict.fromkeys(completed_work)),
            decisions=list(dict.fromkeys(decisions)),
            open_questions=list(dict.fromkeys(open_questions)),
        )
