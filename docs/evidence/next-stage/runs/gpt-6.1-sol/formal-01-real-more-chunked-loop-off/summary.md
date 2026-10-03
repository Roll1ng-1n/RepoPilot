# Stage 4 evaluation

| Model | Engine | Group | Task pass | Successful termination | Recovery | LLM calls / solved | Tokens / solved | Tool failures / solved | Post-solution churn |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| openai/gpt-6.1-sol | repopilot | category:cross-file | 0/1 (0 unavailable) | 0.000 | unsupported | unsupported | unsupported | unsupported | unsupported |
| openai/gpt-6.1-sol | repopilot | overall:all | 0/1 (0 unavailable) | 0.000 | unsupported | unsupported | unsupported | unsupported | unsupported |

Cost per solved includes failed trials. Missing usage makes the corresponding total unavailable.
Compare tokens only within the same model. Detailed distributions and paired counts are in summary.json.

| Model | Category | Left | Right | Both | Left only | Right only | Neither | Unavailable |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |

# Agent Benchmark Summary

| Task | Snapshot Revision | Engine | Status | Success | Steps | Total tokens | Provider/LiteLLM cost | OpenAI Standard estimate | Duration (s) |
| --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| real-more-chunked | 8c1a6ef241b51ff055e89219f050ccf4f15f37f6 | repopilot | BUDGET_EXCEEDED | false | 48 | 505986 | 0.6108359999999999 | null | 962.6252288200003 |

Results are raw development evidence; no performance numbers are prefilled.
