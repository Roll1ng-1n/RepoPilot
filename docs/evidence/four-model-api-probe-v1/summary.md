# Four-model OpenAI-compatible API probe

On 2026-09-04, each requested model completed two minimal Chat Completions requests against the authorized
OpenAI-compatible intermediary: an exact-text response and a required native function call. Automatic retries were
disabled. All eight requests succeeded, and every function call contained JSON object arguments.

| Model | Text latency | Tool latency | Text input/output | Tool input/output | OpenAI Standard estimate |
| --- | ---: | ---: | ---: | ---: | ---: |
| `gpt-5.6-luna` | 2.581s | 3.197s | 4,393 / 5 | 1,495 / 21 | $0.0005176 |
| `gpt-5.6-terra` | 32.931s | 39.700s | 4,391 / 5 | 4,438 / 21 | $0.0110580 |
| `gpt-5.6-sol` | 2.487s | 2.893s | 307 / 5 | 4,438 / 21 | $0.0195000 |
| `gpt-5.5` | 2.011s | 4.347s | 4,393 / 5 | 4,438 / 21 | $0.0276550 |

The total estimate is **$0.0587306**. Costs use the post-reduction OpenAI **Standard** token prices published on the
[official pricing page](https://developers.openai.com/api/docs/pricing), including reported cached-input tokens.
These are estimates for comparison, not intermediary invoice data. The endpoint and credential are intentionally
omitted. The intermediary's hidden prompt made several nominally tiny requests consume thousands of input tokens;
that returned usage is retained rather than replaced with locally predicted token counts.
