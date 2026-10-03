# Stage 4 evaluation

| Model | Engine | Group | Task pass | Successful termination | Recovery | LLM calls / solved | Tokens / solved | Tool failures / solved | Post-solution churn |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| openai/gpt-6.1-sol | repopilot | capability:recovery | 1/1 (0 unavailable) | 1.000 | 1.000 | 35.000 | 338017.000 | 3.000 | unsupported |
| openai/gpt-6.1-sol | repopilot | category:recovery | 1/1 (0 unavailable) | 1.000 | 1.000 | 35.000 | 338017.000 | 3.000 | unsupported |
| openai/gpt-6.1-sol | repopilot | overall:all | 1/1 (0 unavailable) | 1.000 | 1.000 | 35.000 | 338017.000 | 3.000 | unsupported |

Cost per solved includes failed trials. Missing usage makes the corresponding total unavailable.
Compare tokens only within the same model. Detailed distributions and paired counts are in summary.json.

| Model | Category | Left | Right | Both | Left only | Right only | Neither | Unavailable |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |

# Agent Benchmark Summary

| Task | Snapshot Revision | Engine | Status | Success | Steps | Total tokens | Provider/LiteLLM cost | OpenAI Standard estimate | Duration (s) |
| --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| real-cachetools-expire | ca7508fd56103a1b6d6f17c8e93e36c60b44ca25 | repopilot | SUCCEEDED | true | 35 | 338017 | 0.4106852 | null | 309.52069407700037 |

Results are raw development evidence; no performance numbers are prefilled.
