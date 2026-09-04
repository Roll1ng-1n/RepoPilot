"""Small, dependency-light compatibility probes for OpenAI-compatible models.

The probe deliberately uses the Chat Completions API directly.  It is intended to
answer one narrow question before an expensive benchmark run: can a provider
return ordinary text and a native function Tool Call for each configured model?

The client is injectable so the probe can be tested without a network request.
Only normalized response metadata is retained; response bodies, credentials, and
the configured base URL are never written to a report.
"""

from __future__ import annotations

import json
import math
import os
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from typing import Any, Protocol

from repopilot.pricing import OPENAI_STANDARD_PRICING_AS_OF, OPENAI_STANDARD_PRICING_SOURCE

Usage = dict[str, int | None]

_USAGE_KEYS = ("prompt", "completion", "total", "cached", "cache_write", "reasoning")


class ChatCompletionsClient(Protocol):
    """The small part of an OpenAI client used by :class:`ModelProbe`."""

    chat: Any


DEFAULT_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "report_probe",
        "description": "Report that native Tool Calling is available.",
        "parameters": {
            "type": "object",
            "properties": {"result": {"type": "string"}},
            "required": ["result"],
            "additionalProperties": False,
        },
    },
}


def _value(source: Any, key: str) -> Any:
    if source is None:
        return None
    if isinstance(source, Mapping):
        return source.get(key)
    try:
        return getattr(source, key, None)
    except Exception:
        return None


def _integer(value: Any) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return None


def _first_integer(source: Any, keys: Sequence[str]) -> int | None:
    for key in keys:
        value = _integer(_value(source, key))
        if value is not None:
            return value
    return None


def extract_usage(response: Any) -> Usage | None:
    """Normalize common OpenAI/LiteLLM usage shapes.

    The compact field names match the benchmark's model statistics.  Providers
    often omit cache and reasoning details; those fields remain ``None`` instead
    of being inferred.
    """

    usage = _value(response, "usage")
    if usage is None:
        return None
    prompt_details = next(
        (
            _value(usage, key)
            for key in ("prompt_tokens_details", "input_tokens_details", "prompt_token_details")
            if _value(usage, key) is not None
        ),
        None,
    )
    completion_details = next(
        (
            _value(usage, key)
            for key in ("completion_tokens_details", "output_tokens_details", "completion_token_details")
            if _value(usage, key) is not None
        ),
        None,
    )
    return {
        "prompt": _first_integer(usage, ("prompt_tokens", "input_tokens")),
        "completion": _first_integer(usage, ("completion_tokens", "output_tokens")),
        "total": _first_integer(usage, ("total_tokens",)),
        "cached": _first_integer(
            usage,
            ("cached_tokens", "cache_read_tokens"),
        )
        if _first_integer(usage, ("cached_tokens", "cache_read_tokens")) is not None
        else _first_integer(prompt_details, ("cached_tokens", "cache_read_tokens")),
        "cache_write": _first_integer(
            usage,
            ("cache_write_tokens", "cache_creation_input_tokens", "cache_creation_tokens"),
        )
        if _first_integer(usage, ("cache_write_tokens", "cache_creation_input_tokens", "cache_creation_tokens")) is not None
        else _first_integer(
            prompt_details,
            ("cache_write_tokens", "cache_creation_input_tokens", "cache_creation_tokens"),
        ),
        "reasoning": _first_integer(usage, ("reasoning_tokens",))
        if _first_integer(usage, ("reasoning_tokens",)) is not None
        else _first_integer(completion_details, ("reasoning_tokens", "reasoning")),
    }


def _empty_usage() -> Usage:
    return {key: None for key in _USAGE_KEYS}


def extract_provider_cost(response: Any) -> float | None:
    """Return a provider-reported cost when one is present.

    No price table is applied here.  A separately labelled OpenAI Standard
    estimate is produced only when ``repopilot.pricing`` is available.
    """

    sources = [_value(response, "_hidden_params"), _value(response, "usage"), response]
    for source in sources:
        for key in ("response_cost", "cost", "provider_cost", "provider_cost_usd"):
            value = _value(source, key)
            if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value)):
                return float(value)
    return None


def estimate_openai_standard_cost(model: str, usage: Usage | None) -> float | None:
    """Call the optional repository price table without making it mandatory.

    The pricing module is intentionally optional while the campaign is being
    assembled.  The helper accepts either the positional ``(model, usage)``
    contract or the equivalent keyword contract used by likely implementations.
    """

    if usage is None:
        return None
    try:
        pricing = import_module("repopilot.pricing")
        estimator = pricing.estimate_openai_standard_cost
    except (ImportError, AttributeError):
        return None
    try:
        pricing_usage = {
            **usage,
            "prompt_tokens": usage["prompt"],
            "completion_tokens": usage["completion"],
            "cached_tokens": usage["cached"],
            "cache_write_tokens": usage["cache_write"],
        }
        value = estimator(model, pricing_usage)
    except TypeError:
        try:
            value = estimator(model_name=model, usage=pricing_usage)
        except (TypeError, ValueError, KeyError):
            return None
    except (ValueError, KeyError):
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value)):
        return float(value)
    return None


def _choice(response: Any) -> Any:
    choices = _value(response, "choices")
    if isinstance(choices, Sequence) and not isinstance(choices, (str, bytes)) and choices:
        return choices[0]
    return None


def _response_model(response: Any) -> str | None:
    value = _value(response, "model")
    return value if isinstance(value, str) else None


def _finish_reason(response: Any) -> str | None:
    value = _value(_choice(response), "finish_reason")
    return value if isinstance(value, str) else None


def _message(response: Any) -> Any:
    return _value(_choice(response), "message")


def _text_is_valid(response: Any) -> bool:
    content = _value(_message(response), "content")
    if isinstance(content, str):
        return content.strip() == "OK"
    return False


def _tool_call_is_valid(
    response: Any,
    expected_name: str,
    tool: Mapping[str, Any] | None = None,
) -> tuple[bool, str | None]:
    calls = _value(_message(response), "tool_calls")
    if not isinstance(calls, Sequence) or isinstance(calls, (str, bytes)) or not calls:
        return False, None
    parameters = _value(_value(tool, "function"), "parameters")
    required = _value(parameters, "required")
    properties = _value(parameters, "properties")
    names: list[str] = []
    for call in calls:
        call_type = _value(call, "type")
        if call_type is not None and call_type != "function":
            return False, None
        call_id = _value(call, "id")
        function = _value(call, "function")
        name = _value(function, "name")
        arguments = _value(function, "arguments")
        if not isinstance(call_id, str) or not call_id or not isinstance(name, str) or not name:
            return False, None
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except (TypeError, ValueError):
                return False, name
        if not isinstance(arguments, Mapping):
            return False, name
        if isinstance(required, Sequence) and isinstance(properties, Mapping):
            for key in required:
                if not isinstance(key, str) or key not in arguments:
                    return False, name
                schema = _value(properties, key)
                expected_type = _value(schema, "type")
                if expected_type == "string" and not isinstance(arguments[key], str):
                    return False, name
                if expected_type == "boolean" and not isinstance(arguments[key], bool):
                    return False, name
                if expected_type == "object" and not isinstance(arguments[key], Mapping):
                    return False, name
        names.append(name)
    if expected_name not in names:
        return False, names[0] if names else None
    return True, expected_name


def _redact_error(error: BaseException, secrets: Sequence[str]) -> str:
    message = str(error).strip() or type(error).__name__
    values = [secret for secret in secrets if secret]
    for secret in values:
        message = message.replace(secret, "[REDACTED]")
    # Also cover URL variants where a provider includes only the authority or
    # credentials in its exception rather than echoing the complete base URL.
    for secret in values:
        if "://" not in secret:
            continue
        authority = secret.split("://", 1)[1].split("/", 1)[0]
        if authority:
            message = message.replace(authority, "[REDACTED]")
    message = re.sub(r"(?i)(bearer\s+|api[_-]?key\s*[=:]\s*)[^\s,;]+", r"\1[REDACTED]", message)
    return f"{type(error).__name__}: {message}"


@dataclass(frozen=True)
class ProbeAttempt:
    """Normalized result for one text or Tool Calling request."""

    valid: bool
    duration_seconds: float
    response_model: str | None = None
    finish_reason: str | None = None
    usage: Usage | None = None
    provider_cost_usd: float | None = None
    openai_standard_estimate_usd: float | None = None
    tool_call_name: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "duration_seconds": self.duration_seconds,
            "response_model": self.response_model,
            "finish_reason": self.finish_reason,
            "usage": self.usage,
            "provider_cost_usd": self.provider_cost_usd,
            "openai_standard_estimate_usd": self.openai_standard_estimate_usd,
            "tool_call_name": self.tool_call_name,
            "error": self.error,
        }


@dataclass(frozen=True)
class ProbeResult:
    """Results for both compatibility requests made for one model."""

    model: str
    text: ProbeAttempt
    tool_call: ProbeAttempt

    @property
    def passed(self) -> bool:
        return self.text.valid and self.tool_call.valid

    @property
    def text_valid(self) -> bool:
        return self.text.valid

    @property
    def tool_call_valid(self) -> bool:
        return self.tool_call.valid

    def to_dict(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "passed": self.passed,
            "text": self.text.to_dict(),
            "tool_call": self.tool_call.to_dict(),
        }


@dataclass(frozen=True)
class ProbeReport:
    """Serializable collection of model probe results."""

    results: tuple[ProbeResult, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "pricing_basis": {
                "tier": "standard",
                "as_of": OPENAI_STANDARD_PRICING_AS_OF,
                "source": OPENAI_STANDARD_PRICING_SOURCE,
                "note": "Estimate only; not intermediary invoice data.",
            },
            "results": [result.to_dict() for result in self.results],
        }

    def write_json(self, path: str | Path) -> Path:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return destination

    def to_markdown(self) -> str:
        lines = [
            "# Model compatibility probe",
            "",
            "Costs are provider-reported where available; the separate estimate is based on OpenAI Standard pricing "
            f"as of {OPENAI_STANDARD_PRICING_AS_OF} ({OPENAI_STANDARD_PRICING_SOURCE}).",
            "",
            "| Model | Text | Tool Call | Duration (s) | Provider cost (USD) | OpenAI Standard estimate (USD) |",
            "| --- | ---: | ---: | ---: | ---: | ---: |",
        ]
        for result in self.results:
            duration = result.text.duration_seconds + result.tool_call.duration_seconds
            provider_cost = _sum_costs(result.text.provider_cost_usd, result.tool_call.provider_cost_usd)
            standard_cost = _sum_costs(
                result.text.openai_standard_estimate_usd,
                result.tool_call.openai_standard_estimate_usd,
            )
            lines.append(
                f"| {_markdown_cell(result.model)} | {'PASS' if result.text.valid else 'FAIL'} | "
                f"{'PASS' if result.tool_call.valid else 'FAIL'} | {duration:.3f} | "
                f"{_format_cost(provider_cost)} | {_format_cost(standard_cost)} |"
            )
        return "\n".join(lines) + "\n"

    def write_markdown(self, path: str | Path) -> Path:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(self.to_markdown(), encoding="utf-8")
        return destination


def _sum_costs(first: float | None, second: float | None) -> float | None:
    if first is None or second is None:
        return None
    return first + second


def _format_cost(value: float | None) -> str:
    return "—" if value is None else f"{value:.6f}"


def _markdown_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


class ModelProbe:
    """Run two direct Chat Completions compatibility requests per model."""

    def __init__(
        self,
        *,
        client: ChatCompletionsClient | None = None,
        client_factory: Callable[[], ChatCompletionsClient] | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        request_kwargs: Mapping[str, Any] | None = None,
        text_request_kwargs: Mapping[str, Any] | None = None,
        tool_request_kwargs: Mapping[str, Any] | None = None,
        text_prompt: str = "Reply with the single word OK.",
        tool_prompt: str = "Call the report_probe tool with result set to OK.",
        tool: Mapping[str, Any] | None = None,
    ) -> None:
        if client is not None and client_factory is not None:
            raise ValueError("Pass either client or client_factory, not both.")
        self._api_key = api_key if api_key is not None else os.getenv("REPOPILOT_API_KEY")
        self._base_url = base_url if base_url is not None else os.getenv("REPOPILOT_BASE_URL")
        if client is not None:
            self._client = client
        elif client_factory is not None:
            self._client = client_factory()
        else:
            from openai import OpenAI

            self._client = OpenAI(
                api_key=self._api_key,
                base_url=self._base_url,
                timeout=60.0,
                max_retries=0,
            )
        self._request_kwargs = dict(request_kwargs or {})
        self._text_request_kwargs = dict(text_request_kwargs or {})
        self._tool_request_kwargs = dict(tool_request_kwargs or {})
        self._text_prompt = text_prompt
        self._tool_prompt = tool_prompt
        self._tool = dict(tool or DEFAULT_TOOL)

    def run(self, models: Sequence[str]) -> ProbeReport:
        """Probe models in order, continuing after a provider or parsing error."""

        return ProbeReport(tuple(self.probe_model(model) for model in models))

    def probe_model(self, model: str) -> ProbeResult:
        text = self._request(model, self._text_prompt, tool_call=False)
        tool_call = self._request(model, self._tool_prompt, tool_call=True)
        return ProbeResult(model=model, text=text, tool_call=tool_call)

    def _request(self, model: str, prompt: str, *, tool_call: bool) -> ProbeAttempt:
        import time

        started = time.monotonic()
        request = {"max_tokens": 64 if tool_call else 16, **self._request_kwargs}
        request.update(self._tool_request_kwargs if tool_call else self._text_request_kwargs)
        request.update({"model": model, "messages": [{"role": "user", "content": prompt}]})
        if tool_call:
            request.update({"tools": [self._tool], "tool_choice": "required"})
        else:
            request.pop("tools", None)
            request.pop("tool_choice", None)
        try:
            response = self._client.chat.completions.create(**request)
            usage = extract_usage(response)
            normalized_usage = usage if usage is not None else _empty_usage()
            provider_cost = extract_provider_cost(response)
            standard_cost = estimate_openai_standard_cost(model, usage)
            if tool_call:
                valid, name = _tool_call_is_valid(response, self._tool["function"]["name"], self._tool)
            else:
                valid, name = _text_is_valid(response), None
            return ProbeAttempt(
                valid=valid,
                duration_seconds=time.monotonic() - started,
                response_model=_response_model(response),
                finish_reason=_finish_reason(response),
                usage=normalized_usage,
                provider_cost_usd=provider_cost,
                openai_standard_estimate_usd=standard_cost,
                tool_call_name=name,
            )
        except Exception as error:
            return ProbeAttempt(
                valid=False,
                duration_seconds=time.monotonic() - started,
                error=_redact_error(error, (self._api_key or "", self._base_url or "")),
            )


def run_model_probe(
    models: Sequence[str],
    *,
    client: ChatCompletionsClient | None = None,
    client_factory: Callable[[], ChatCompletionsClient] | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
    request_kwargs: Mapping[str, Any] | None = None,
    text_request_kwargs: Mapping[str, Any] | None = None,
    tool_request_kwargs: Mapping[str, Any] | None = None,
) -> ProbeReport:
    """Convenience wrapper for callers that do not need a ``ModelProbe`` object."""

    return ModelProbe(
        client=client,
        client_factory=client_factory,
        api_key=api_key,
        base_url=base_url,
        request_kwargs=request_kwargs,
        text_request_kwargs=text_request_kwargs,
        tool_request_kwargs=tool_request_kwargs,
    ).run(models)


__all__ = [
    "DEFAULT_TOOL",
    "ModelProbe",
    "ProbeAttempt",
    "ProbeReport",
    "ProbeResult",
    "extract_provider_cost",
    "extract_usage",
    "estimate_openai_standard_cost",
    "run_model_probe",
]
