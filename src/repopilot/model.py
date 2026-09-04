"""Native Tool Calling model port plus the LiteLLM adapter."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from numbers import Real
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
    usage: dict[str, int | None] | None = None
    cost: float | None = None


class ToolCallingModel(Protocol):
    """Model boundary for a complete Agent Run."""

    model_name: str

    def complete(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> AssistantTurn: ...


class LiteLLMToolCallingModel:
    """Adapter for providers exposed through LiteLLM's OpenAI-compatible Tool Calling API."""

    def __init__(
        self,
        *,
        model_name: str,
        api_key: str | None = None,
        base_url: str | None = None,
        model_kwargs: dict[str, Any] | None = None,
    ):
        self.model_name = model_name
        self._api_key = api_key
        self._base_url = base_url
        self._model_kwargs = dict(model_kwargs or {})

    def complete(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> AssistantTurn:
        import litellm  # type: ignore[import-not-found]

        request_options: dict[str, Any] = {
            **self._model_kwargs,
            "model": self.model_name,
            "messages": messages,
            "tools": tools,
        }
        if self._api_key:
            request_options["api_key"] = self._api_key
        if self._base_url:
            request_options["api_base"] = self._base_url
        response = litellm.completion(**request_options)
        message = response.choices[0].message
        return AssistantTurn(
            content=getattr(message, "content", None),
            tool_calls=[self._to_tool_call(tool_call) for tool_call in (getattr(message, "tool_calls", None) or [])],
            usage=self._usage(response),
            cost=self._cost(response, litellm),
        )

    @classmethod
    def _usage(cls, response: Any) -> dict[str, int | None] | None:
        try:
            usage = cls._value(response, "usage")
        except Exception:
            return None
        if usage is None:
            return None
        return {
            "prompt_tokens": cls._token_value(usage, "prompt_tokens", "input_tokens"),
            "completion_tokens": cls._token_value(usage, "completion_tokens", "output_tokens"),
            "total_tokens": cls._token_value(usage, "total_tokens"),
            # Providers do not agree on where these optional usage details
            # live.  Keep them in the normalized response, including an
            # explicit null when the provider did not report them.
            "cached_tokens": cls._token_value(
                usage,
                "cached_tokens",
                "cache_read_tokens",
                "cache_read_input_tokens",
                "cached_input_tokens",
            ),
            "cache_write_tokens": cls._token_value(
                usage,
                "cache_write_tokens",
                "cache_write_input_tokens",
                "cache_creation_input_tokens",
                "cache_creation_tokens",
            ),
            "reasoning_tokens": cls._token_value(usage, "reasoning_tokens", "reasoning"),
        }

    def _cost(self, response: Any, litellm: Any) -> float | None:
        """Return provider/LiteLLM cost when available, without making a price estimate."""
        try:
            hidden_params = self._value(response, "_hidden_params")
            for source in (hidden_params, self._value(response, "usage"), response):
                value = self._value(source, "response_cost")
                if value is None:
                    value = self._value(source, "cost")
                if isinstance(value, Real) and not isinstance(value, bool):
                    return float(value)
            value = litellm.cost_calculator.completion_cost(response, model=self.model_name)
            return float(value) if isinstance(value, Real) and not isinstance(value, bool) else None
        except Exception:
            return None

    @staticmethod
    def _value(source: Any, key: str) -> Any:
        if isinstance(source, dict):
            return source.get(key)
        try:
            return getattr(source, key, None)
        except Exception:
            return None

    @classmethod
    def _token_value(cls, usage: Any, *keys: str) -> int | None:
        for key in keys:
            value = cls._value(usage, key)
            if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                return value
        # OpenAI-compatible providers commonly put cache and reasoning
        # counters in prompt/completion token detail objects.  Looking in all
        # known detail objects keeps the adapter tolerant of either dict or
        # SDK-object response shapes.
        for details_key in (
            "prompt_tokens_details",
            "input_tokens_details",
            "prompt_token_details",
            "input_token_details",
            "completion_tokens_details",
            "output_tokens_details",
            "completion_token_details",
            "output_token_details",
        ):
            details = cls._value(usage, details_key)
            for key in keys:
                value = cls._value(details, key)
                if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                    return value
        return None

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
