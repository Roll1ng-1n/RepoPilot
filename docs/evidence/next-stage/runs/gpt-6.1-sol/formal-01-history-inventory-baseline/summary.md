# Stage 4 evaluation

| Model | Engine | Group | Task pass | Successful termination | Recovery | LLM calls / solved | Tokens / solved | Tool failures / solved | Post-solution churn |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| openai/gpt-6.1-sol | baseline | capability:recovery | 1/1 (0 unavailable) | 1.000 | 1.000 | 11.000 | 213200.000 | 3.000 | unsupported |
| openai/gpt-6.1-sol | baseline | category:recovery | 1/1 (0 unavailable) | 1.000 | 1.000 | 11.000 | 213200.000 | 3.000 | unsupported |
| openai/gpt-6.1-sol | baseline | overall:all | 1/1 (0 unavailable) | 1.000 | 1.000 | 11.000 | 213200.000 | 3.000 | unsupported |

Cost per solved includes failed trials. Missing usage makes the corresponding total unavailable.
Compare tokens only within the same model. Detailed distributions and paired counts are in summary.json.

| Model | Category | Left | Right | Both | Left only | Right only | Neither | Unavailable |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |

# Agent Benchmark Summary

| Task | Snapshot Revision | Engine | Status | Success | Steps | Total tokens | Provider/LiteLLM cost | OpenAI Standard estimate | Duration (s) |
| --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| history-inventory | issue24-v1 | baseline | Submitted | true | 11 | 213200 | 0.14259040000000003 | null | 392.4416187789993 |

Results are raw development evidence; no performance numbers are prefilled.
