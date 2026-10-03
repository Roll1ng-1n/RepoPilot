# Stage 4 evaluation

| Model | Engine | Group | Task pass | Successful termination | Recovery | LLM calls / solved | Tokens / solved | Tool failures / solved | Post-solution churn |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| openai/gpt-6.1-sol | baseline | category:cross-file | 1/1 (0 unavailable) | 1.000 | unsupported | 11.000 | 139061.000 | 2.000 | unsupported |
| openai/gpt-6.1-sol | baseline | overall:all | 1/1 (0 unavailable) | 1.000 | unsupported | 11.000 | 139061.000 | 2.000 | unsupported |

Cost per solved includes failed trials. Missing usage makes the corresponding total unavailable.
Compare tokens only within the same model. Detailed distributions and paired counts are in summary.json.

| Model | Category | Left | Right | Both | Left only | Right only | Neither | Unavailable |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |

# Agent Benchmark Summary

| Task | Snapshot Revision | Engine | Status | Success | Steps | Total tokens | Provider/LiteLLM cost | OpenAI Standard estimate | Duration (s) |
| --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| real-more-chunked | 8c1a6ef241b51ff055e89219f050ccf4f15f37f6 | baseline | Submitted | true | 11 | 139061 | 0.093322 | null | 539.2265829079997 |

Results are raw development evidence; no performance numbers are prefilled.
