"""OpenAI Standard token-price estimates for the real-model benchmark.

The values in this module are a benchmark estimate based on the public OpenAI
Standard pricing table.  They are deliberately separate from provider- or
LiteLLM-reported costs: a value returned here is not an invoice from an
OpenAI-compatible relay.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

# OpenAI's long-context surcharge starts when a prompt is greater than 272K
# input tokens.  Keep this as a token count instead of a float such as 272K so
# callers can make the boundary decision without rounding.
STANDARD_CONTEXT_THRESHOLD_TOKENS = 272_000
OPENAI_STANDARD_ESTIMATE_LABEL = "OpenAI Standard price estimate"
OPENAI_STANDARD_PRICING_AS_OF = "2026-09-04"
OPENAI_STANDARD_PRICING_SOURCE = "https://developers.openai.com/api/docs/pricing"


@dataclass(frozen=True)
class StandardTokenRates:
    """USD per one million tokens for one Standard pricing tier."""

    input_usd_per_million: float
    cached_input_usd_per_million: float
    cache_write_usd_per_million: float | None
    output_usd_per_million: float

    # Short aliases keep the object pleasant to use when rendering a report,
    # while the canonical names make the units explicit.
    @property
    def input_per_million(self) -> float:
        return self.input_usd_per_million

    @property
    def cached_input_per_million(self) -> float:
        return self.cached_input_usd_per_million

    @property
    def cache_write_per_million(self) -> float | None:
        return self.cache_write_usd_per_million

    @property
    def output_per_million(self) -> float:
        return self.output_usd_per_million


@dataclass(frozen=True)
class OpenAIStandardModelPricing:
    """Short- and long-context Standard rates for one supported model."""

    short: StandardTokenRates
    long: StandardTokenRates | None = None


def _rates(
    input_price: float,
    cached_input_price: float,
    cache_write_price: float | None,
    output_price: float,
) -> StandardTokenRates:
    return StandardTokenRates(
        input_usd_per_million=input_price,
        cached_input_usd_per_million=cached_input_price,
        cache_write_usd_per_million=cache_write_price,
        output_usd_per_million=output_price,
    )


# Prices are USD per 1M tokens, from the public OpenAI API Standard table.
# The long tier is priced for the complete request, as stated by OpenAI.
OPENAI_STANDARD_PRICING: dict[str, OpenAIStandardModelPricing] = {
    "gpt-5.6-sol": OpenAIStandardModelPricing(
        short=_rates(4.0, 0.4, 5.0, 20.0),
        long=_rates(8.0, 0.8, 10.0, 30.0),
    ),
    "gpt-5.6-terra": OpenAIStandardModelPricing(
        short=_rates(2.0, 0.2, 2.5, 12.0),
        long=_rates(4.0, 0.4, 5.0, 18.0),
    ),
    "gpt-5.6-luna": OpenAIStandardModelPricing(
        short=_rates(0.2, 0.02, 0.25, 1.2),
        long=_rates(0.4, 0.04, 0.5, 1.8),
    ),
    # GPT-5.5 has published long-context rates, but the table does not publish
    # a separate cache-write price for it.
    "gpt-5.5": OpenAIStandardModelPricing(
        short=_rates(5.0, 0.5, None, 30.0),
        long=_rates(10.0, 1.0, None, 45.0),
    ),
}

# A descriptive alias for callers that prefer the shorter name.
STANDARD_PRICING = OPENAI_STANDARD_PRICING


def normalize_model_name(model_name: str) -> str:
    """Return the catalog key for a direct or ``openai/`` model name."""

    if not isinstance(model_name, str):
        raise TypeError("model_name must be a string.")
    normalized = model_name.strip()
    if normalized.startswith("openai/"):
        normalized = normalized[len("openai/") :]
    if normalized not in OPENAI_STANDARD_PRICING:
        supported = ", ".join(OPENAI_STANDARD_PRICING)
        raise ValueError(f"Unsupported OpenAI Standard estimate model {model_name!r}; supported: {supported}.")
    return normalized


def get_openai_standard_rates(model_name: str, prompt_tokens: int = 0) -> StandardTokenRates | None:
    """Get the applicable Standard rates for a model and prompt size.

    ``None`` means that OpenAI does not publish a rate for that tier.
    ``prompt_tokens`` is only used for selecting the tier and must be
    non-negative.
    """

    if not isinstance(prompt_tokens, int) or isinstance(prompt_tokens, bool) or prompt_tokens < 0:
        raise ValueError("prompt_tokens must be a non-negative integer.")
    pricing = OPENAI_STANDARD_PRICING[normalize_model_name(model_name)]
    if prompt_tokens <= STANDARD_CONTEXT_THRESHOLD_TOKENS:
        return pricing.short
    return pricing.long


# Alias useful to integrations that call the function without the provider
# name in the identifier.
get_standard_rates = get_openai_standard_rates


def estimate_openai_standard_cost(model_name: str, usage: Mapping[str, Any] | None) -> float | None:
    """Estimate one response's cost in USD using OpenAI Standard pricing.

    The input mapping may use Chat Completions names (``prompt_tokens`` and
    ``completion_tokens``) or Responses names (``input_tokens`` and
    ``output_tokens``).  Cached-token details are read from either top-level
    fields or ``prompt_tokens_details``/``input_tokens_details``.  Cache-write
    fields are accepted when a compatible provider exposes them separately.

    Missing usage or missing required token counts returns ``None``.  If cache
    details are absent, all prompt tokens are charged as ordinary input.  A
    model with no published rate for the selected context tier also returns
    ``None``.  If a provider reports cache-write tokens for a model with no
    published cache-write rate, the estimate is unavailable and returns
    ``None``.  The result is an OpenAI Standard estimate, never a provider
    invoice or a substitute for provider-reported ``cost``.
    """

    if usage is None:
        return None
    if not isinstance(usage, Mapping):
        raise TypeError("usage must be a mapping or None.")

    prompt_tokens = _first_token(usage, "prompt_tokens", "input_tokens")
    completion_tokens = _first_token(usage, "completion_tokens", "output_tokens")
    if prompt_tokens is None or completion_tokens is None:
        return None

    cached_tokens = _detail_token(
        usage,
        ("cached_tokens", "cache_read_tokens", "cache_read_input_tokens", "cached_input_tokens"),
    )
    cache_write_tokens = _detail_token(
        usage,
        ("cache_write_tokens", "cache_write_input_tokens", "cache_creation_input_tokens", "cache_creation_tokens"),
    )
    cached_tokens = 0 if cached_tokens is None else cached_tokens
    cache_write_tokens = 0 if cache_write_tokens is None else cache_write_tokens
    if cached_tokens > prompt_tokens:
        return None

    rates = get_openai_standard_rates(model_name, prompt_tokens)
    if rates is None:
        return None
    if cache_write_tokens and rates.cache_write_usd_per_million is None:
        return None

    # Providers can expose cache-write tokens separately from prompt_tokens;
    # in that representation the cache-write amount is an additional billed
    # category.  This also preserves the requested fallback: with no cache
    # details, the complete prompt is ordinary input.
    ordinary_input_tokens = prompt_tokens - cached_tokens
    cost = (
        ordinary_input_tokens * rates.input_usd_per_million
        + cached_tokens * rates.cached_input_usd_per_million
        + cache_write_tokens * (rates.cache_write_usd_per_million or 0.0)
        + completion_tokens * rates.output_usd_per_million
    ) / 1_000_000
    return float(cost)


# Keep a concise spelling available for campaign code and downstream users.
estimate_standard_cost = estimate_openai_standard_cost


def _first_token(source: Mapping[str, Any], *keys: str) -> int | None:
    for key in keys:
        value = source.get(key)
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            return value
    return None


def _detail_token(source: Mapping[str, Any], keys: tuple[str, ...]) -> int | None:
    direct = _first_token(source, *keys)
    if direct is not None:
        return direct
    for details_key in ("prompt_tokens_details", "input_tokens_details", "prompt_token_details", "input_token_details"):
        details = source.get(details_key)
        if isinstance(details, Mapping):
            nested = _first_token(details, *keys)
            if nested is not None:
                return nested
    return None


__all__ = [
    "OPENAI_STANDARD_ESTIMATE_LABEL",
    "OPENAI_STANDARD_PRICING",
    "OPENAI_STANDARD_PRICING_AS_OF",
    "OPENAI_STANDARD_PRICING_SOURCE",
    "STANDARD_CONTEXT_THRESHOLD_TOKENS",
    "STANDARD_PRICING",
    "OpenAIStandardModelPricing",
    "StandardTokenRates",
    "estimate_openai_standard_cost",
    "estimate_standard_cost",
    "get_openai_standard_rates",
    "get_standard_rates",
    "normalize_model_name",
]
