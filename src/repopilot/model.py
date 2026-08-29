"""Native Tool Calling model port plus the LiteLLM adapter."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class ToolCall:
    """One OpenAI-compatible structured tool request."""

    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class AssistantTurn:
    """A model response containing native Tool Calls rather than parsed text actions."""

    content: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)


class ToolCallingModel(Protocol):
    """Model boundary for a complete Agent Run."""

    model_name: str

    def complete(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> AssistantTurn: ...


class LiteLLMToolCallingModel:
    """Adapter for providers exposed through LiteLLM's OpenAI-compatible Tool Calling API."""

    def __init__(self, *, model_name: str, api_key: str | None = None, base_url: str | None = None):
        self.model_name = model_name
        self._api_key = api_key
        self._base_url = base_url

    def complete(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> AssistantTurn:
        import litellm  # type: ignore[import-not-found]

        request_options: dict[str, Any] = {"model": self.model_name, "messages": messages, "tools": tools}
        if self._api_key:
            request_options["api_key"] = self._api_key
        if self._base_url:
            request_options["api_base"] = self._base_url
        response = litellm.completion(**request_options)
        message = response.choices[0].message
        return AssistantTurn(
            content=getattr(message, "content", None),
            tool_calls=[self._to_tool_call(tool_call) for tool_call in (getattr(message, "tool_calls", None) or [])],
        )

    @staticmethod
    def _to_tool_call(tool_call: Any) -> ToolCall:
        function = tool_call.function
        arguments = function.arguments
        if not isinstance(arguments, str):
            raise TypeError("Native Tool Call arguments must be a JSON object string.")
        parsed_arguments = json.loads(arguments)
        if not isinstance(parsed_arguments, dict):
            raise TypeError("Native Tool Call arguments must decode to an object.")
        return ToolCall(id=tool_call.id, name=function.name, arguments=parsed_arguments)
