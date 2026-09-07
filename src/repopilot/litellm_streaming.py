"""Streaming-capable LiteLLM model used by the mini-SWE-agent baseline.

Some OpenAI-compatible intermediaries restrict an account to streaming requests
only.  The upstream ``minisweagent.models.litellm_model.LitellmModel`` is fixed
as a vendored baseline and always issues a non-streaming ``litellm.completion``
call, so it cannot interoperate with such an account.  This class lives in the
``repopilot`` package (per ``UPSTREAM.md``: RepoPilot capabilities belong in a
separate package unless an upstream interface blocks a reasonable extension)
and re-uses the same chunk re-aggregation as
:func:`repopilot.model.stream_or_plain_completion`.  Everything else about the
model (cost tracking, format-error persistence, retry) is inherited unchanged.
"""

from __future__ import annotations

from typing import Any

from minisweagent.models.litellm_model import LitellmModel
from minisweagent.models.utils.actions_toolcall import BASH_TOOL

from repopilot.model import stream_or_plain_completion


class StreamingLitellmModel(LitellmModel):
    """``LitellmModel`` that forces ``stream=true`` and re-aggregates chunks.

    A benchmark invocation may opt in by placing ``{"stream": true}`` in the
    model kwargs.  When the flag is set the query returns the same aggregated
    ``ModelResponse`` shape as the non-streaming upstream path, so the baseline
    agent, trajectory persistence, and cost accounting are unchanged.
    """

    def _query(self, messages: list[dict[str, str]], **kwargs: Any):
        import litellm  # type: ignore[import-not-found]

        options: dict[str, Any] = {**self.config.model_kwargs, **kwargs}
        force_stream = bool(options.pop("stream", False))
        try:
            return stream_or_plain_completion(
                litellm,
                {
                    "model": self.config.model_name,
                    "messages": messages,
                    "tools": [BASH_TOOL],
                    **options,
                },
                force_stream=force_stream,
            )
        except litellm.exceptions.AuthenticationError as error:  # type: ignore[attr-defined]
            # Match the upstream `_query` UX for a missing or bad key.
            error.message += " You can permanently set your API key with `mini-extra config set KEY VALUE`."  # type: ignore[attr-defined]
            raise error
