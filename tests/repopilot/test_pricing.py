from __future__ import annotations

import pytest

from repopilot.pricing import (
    STANDARD_CONTEXT_THRESHOLD_TOKENS,
    estimate_openai_standard_cost,
    get_openai_standard_rates,
)


@pytest.mark.parametrize(
    ("model", "input_price", "cached_price", "cache_write_price", "output_price"),
    [
        ("gpt-5.6-sol", 4.0, 0.4, 5.0, 20.0),
        ("openai/gpt-5.6-terra", 2.0, 0.2, 2.5, 12.0),
        ("gpt-5.6-luna", 0.2, 0.02, 0.25, 1.2),
        ("gpt-5.5", 5.0, 0.5, None, 30.0),
    ],
)
def test_standard_catalog_supports_models_and_openai_prefix(
    model: str,
    input_price: float,
    cached_price: float,
    cache_write_price: float | None,
    output_price: float,
) -> None:
    rates = get_openai_standard_rates(model)

    assert rates is not None
    assert rates.input_usd_per_million == input_price
    assert rates.cached_input_usd_per_million == cached_price
    assert rates.cache_write_usd_per_million == cache_write_price
    assert rates.output_usd_per_million == output_price


def test_estimate_uses_required_tokens_and_falls_back_to_uncached_input() -> None:
    # $4/M input + $20/M output for Sol's short-context tier.
    assert estimate_openai_standard_cost("gpt-5.6-sol", {"prompt_tokens": 100_000, "completion_tokens": 100_000}) == 2.4
    assert estimate_openai_standard_cost("gpt-5.6-sol", None) is None
    assert estimate_openai_standard_cost("gpt-5.6-sol", {"prompt_tokens": 100}) is None


def test_estimate_reads_nested_cache_details_and_responses_token_names() -> None:
    usage = {
        "input_tokens": 100_000,
        "output_tokens": 100_000,
        "input_tokens_details": {"cached_tokens": 20_000, "cache_write_tokens": 10_000},
    }

    # The provider exposes cache writes as a separate billed category.
    expected = (80_000 * 0.2 + 20_000 * 0.02 + 10_000 * 0.25 + 100_000 * 1.2) / 1_000_000
    assert estimate_openai_standard_cost("gpt-5.6-luna", usage) == pytest.approx(expected)


def test_estimate_switches_to_long_tier_after_272k_and_uses_gpt55_long_rates() -> None:
    short = estimate_openai_standard_cost(
        "gpt-5.6-terra",
        {"prompt_tokens": STANDARD_CONTEXT_THRESHOLD_TOKENS, "completion_tokens": 0},
    )
    long = estimate_openai_standard_cost(
        "gpt-5.6-terra",
        {"prompt_tokens": STANDARD_CONTEXT_THRESHOLD_TOKENS + 1, "completion_tokens": 0},
    )

    assert short == pytest.approx(STANDARD_CONTEXT_THRESHOLD_TOKENS * 2.0 / 1_000_000)
    assert long == pytest.approx((STANDARD_CONTEXT_THRESHOLD_TOKENS + 1) * 4.0 / 1_000_000)
    gpt55_long = estimate_openai_standard_cost(
        "gpt-5.5", {"prompt_tokens": STANDARD_CONTEXT_THRESHOLD_TOKENS + 1, "completion_tokens": 1}
    )
    assert gpt55_long == pytest.approx((10.0 * (STANDARD_CONTEXT_THRESHOLD_TOKENS + 1) + 45.0) / 1_000_000)


def test_gpt55_cache_write_without_a_published_rate_is_unavailable() -> None:
    assert (
        estimate_openai_standard_cost(
            "gpt-5.5",
            {
                "prompt_tokens": 100,
                "completion_tokens": 1,
                "cache_write_tokens": 10,
            },
        )
        is None
    )


def test_unknown_model_is_rejected() -> None:
    with pytest.raises(ValueError, match="Unsupported OpenAI Standard estimate model"):
        estimate_openai_standard_cost("gpt-unknown", {"prompt_tokens": 1, "completion_tokens": 1})
