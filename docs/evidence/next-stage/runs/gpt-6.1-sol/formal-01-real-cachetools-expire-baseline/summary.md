# Stage 4 evaluation

| Model | Engine | Group | Task pass | Successful termination | Recovery | LLM calls / solved | Tokens / solved | Tool failures / solved | Post-solution churn |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| openai/gpt-6.1-sol | baseline | capability:recovery | 1/1 (0 unavailable) | 1.000 | 1.000 | 8.000 | 90036.000 | 4.000 | unsupported |
| openai/gpt-6.1-sol | baseline | category:recovery | 1/1 (0 unavailable) | 1.000 | 1.000 | 8.000 | 90036.000 | 4.000 | unsupported |
| openai/gpt-6.1-sol | baseline | overall:all | 1/1 (0 unavailable) | 1.000 | 1.000 | 8.000 | 90036.000 | 4.000 | unsupported |

Cost per solved includes failed trials. Missing usage makes the corresponding total unavailable.
Compare tokens only within the same model. Detailed distributions and paired counts are in summary.json.

| Model | Category | Left | Right | Both | Left only | Right only | Neither | Unavailable |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |

# Agent Benchmark Summary

| Task | Snapshot Revision | Engine | Status | Success | Steps | Total tokens | Provider/LiteLLM cost | OpenAI Standard estimate | Duration (s) |
| --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| real-cachetools-expire | ca7508fd56103a1b6d6f17c8e93e36c60b44ca25 | baseline | Submitted | true | 8 | 90036 | 0.06047040000000001 | null | 362.10781829000007 |

Results are raw development evidence; no performance numbers are prefilled.
