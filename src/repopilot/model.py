"""Native Tool Calling model port plus the LiteLLM adapter."""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from numbers import Real
from typing import Any, Protocol


class ModelProtocolError(ValueError):
    """A response cannot be consumed safely as native Tool Calling."""


@dataclass(frozen=True)
class ToolCall:
    """One OpenAI-compatible structured tool request."""

    id: str
    name: str
    arguments: dict[str, Any]
    protocol_error: str | None = None
    raw_arguments: str | None = None


@dataclass(frozen=True)
class AssistantTurn:
    """A model response containing native Tool Calls rather than parsed text actions."""

    content: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: dict[str, int | None] | None = None
    cost: float | None = None
    finish_reason: str | None = None


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
        force_stream: bool = False,
    ):
        self.model_name = model_name
        self._api_key = api_key
        self._base_url = base_url
        self._model_kwargs = dict(model_kwargs or {})
        self.force_stream = force_stream
        self.stream_observer = None

    def complete(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]], *, timeout_seconds=None
    ) -> AssistantTurn:
        import litellm  # type: ignore[import-not-found]

        request_options: dict[str, Any] = {
            **self._model_kwargs,
            "model": self.model_name,
            "messages": messages,
            "tools": tools,
        }
        request_options.setdefault("max_tokens", 4096)
        if timeout_seconds is not None:
            request_options["timeout"] = min(float(request_options.get("timeout", timeout_seconds)), timeout_seconds)
        if self._api_key:
            request_options["api_key"] = self._api_key
        if self._base_url:
            request_options["api_base"] = self._base_url
        response = stream_or_plain_completion(
            litellm, request_options, force_stream=self.force_stream, observer=self.stream_observer
        )
        choices = self._value(response, "choices")
        if not isinstance(choices, list) or not choices or self._value(choices[0], "message") is None:
            raise ModelProtocolError("Model response has no choices/message.")
        message = self._value(choices[0], "message")
        finish_reason = self._value(choices[0], "finish_reason")
        calls = [self._to_tool_call(call) for call in (self._value(message, "tool_calls") or [])]
        if finish_reason in {"length", "content_filter"}:
            calls = [
                ToolCall(c.id, c.name, c.arguments, "Response was truncated or filtered; resend complete arguments.")
                for c in calls
            ]
        return AssistantTurn(
            content=self._value(message, "content"),
            tool_calls=calls,
            finish_reason=finish_reason,
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
        value = LiteLLMToolCallingModel._value
        function = value(tool_call, "function")
        identifier = value(tool_call, "id")
        name = value(function, "name")
        if not isinstance(identifier, str) or not identifier or not isinstance(name, str) or not name:
            raise ModelProtocolError("Native Tool Call requires a stable ID and function name.")
        arguments = value(function, "arguments")
        try:
            if not isinstance(arguments, str):
                raise TypeError("Native Tool Call arguments must be a JSON object string.")
            parsed_arguments = json.loads(arguments)
            if not isinstance(parsed_arguments, dict):
                raise TypeError("Native Tool Call arguments must decode to an object.")
        except (TypeError, ValueError):
            return ToolCall(
                id=identifier,
                name=name,
                arguments={},
                protocol_error="Invalid native Tool Call JSON object; supply complete valid arguments.",
                raw_arguments=arguments if isinstance(arguments, str) else repr(arguments),
            )
        return ToolCall(id=identifier, name=name, arguments=parsed_arguments)


def stream_chunk_record(sequence: int, chunk: Any) -> dict[str, Any]:
    """Capture public SDK fields before aggregation, without transport headers."""
    value = LiteLLMToolCallingModel._value
    payload = {key: value(chunk, key) for key in ("id", "model", "created", "choices", "usage")}

    def serialize(item):
        if hasattr(item, "model_dump"):
            return item.model_dump(mode="json")
        return vars(item)

    return {
        "sequence": sequence,
        "sdk_created_at": (value(chunk, "_hidden_params") or {}).get("created_at"),
        "chunk": json.loads(json.dumps(payload, default=serialize)),
    }


def stream_or_plain_completion(
    litellm: Any,
    request_options: dict[str, Any],
    *,
    force_stream: bool = False,
    observer=None,
) -> Any:
    """Issue a Chat Completions request and return a non-streamed model response.

    Some OpenAI-compatible intermediaries restrict an account to streaming
    requests only (``"restricted to streaming requests only"``).  Forcing
    ``stream=true`` there and re-aggregating the chunks with
    :func:`litellm.stream_chunk_builder` returns the same
    ``response.choices[0].message``/``usage`` shape both engine paths expect, so
    RepoPilot can interoperate with such accounts without changing the model
    boundary.  ``force_stream`` always streams; otherwise a ``"stream"`` entry in
    the request options opts in.
    """

    stream = bool(force_stream or request_options.get("stream"))
    options = dict(request_options)
    if stream:
        options.pop("stream", None)
        options.setdefault("stream_options", {"include_usage": True})
        response = litellm.completion(stream=True, **options)
        # SDK response objects can themselves be iterable (key/value pairs).
        value = LiteLLMToolCallingModel._value
        choices = value(response, "choices")
        if choices and value(choices[0], "message") is not None:
            return response
        chunks = []
        size = 0
        try:
            for chunk in response:
                size += len(str(chunk))
                if len(chunks) >= 100_000 or size > 16_000_000:
                    raise ModelProtocolError("Stream exceeded the aggregation limit.")
                if observer is not None:
                    observer(len(chunks), chunk)
                # Stream order is authoritative. Some LiteLLM versions sort by
                # hidden timestamps, which can move delayed/buffered fragments.
                # Normalize only the builder's copies, preserving diagnostics.
                ordered = copy.deepcopy(chunk)
                hidden = dict(value(ordered, "_hidden_params") or {})
                hidden["created_at"] = len(chunks) + 1
                if isinstance(ordered, dict):
                    ordered["_hidden_params"] = hidden
                elif hasattr(ordered, "_hidden_params"):
                    ordered._hidden_params = hidden
                chunks.append(ordered)
        except (TypeError, ValueError) as error:
            raise ModelProtocolError("Invalid streaming response shape.") from error
        finally:
            close = getattr(response, "close", None)
            if callable(close):
                close()
        if not chunks:
            raise ModelProtocolError("Model returned an empty stream.")
        plain = litellm.stream_chunk_builder(chunks)
        if plain is None:
            raise ModelProtocolError("Stream aggregation returned no response.")
        return plain
    return litellm.completion(**options)
