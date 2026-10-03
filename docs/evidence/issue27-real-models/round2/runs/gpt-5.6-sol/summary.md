# Stage 4 evaluation

| Model | Engine | Group | Task pass | Successful termination | Recovery | LLM calls / solved | Tokens / solved | Tool failures / solved | Post-solution churn |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| openai/gpt-5.6-sol | repopilot | capability:recovery | 1/1 (0 unavailable) | 1.000 | 1.000 | 9.000 | 40030.000 | 1.000 | unsupported |
| openai/gpt-5.6-sol | repopilot | category:recovery | 1/1 (0 unavailable) | 1.000 | 1.000 | 9.000 | 40030.000 | 1.000 | unsupported |
| openai/gpt-5.6-sol | repopilot | overall:all | 1/1 (0 unavailable) | 1.000 | 1.000 | 9.000 | 40030.000 | 1.000 | unsupported |

Cost per solved includes failed trials. Missing usage makes the corresponding total unavailable.
Compare tokens only within the same model. Detailed distributions and paired counts are in summary.json.

| Model | Category | Left | Right | Both | Left only | Right only | Neither | Unavailable |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |

# Agent Benchmark Summary

| Task | Snapshot Revision | Engine | Status | Success | Steps | Total tokens | Provider/LiteLLM cost | OpenAI Standard estimate | Duration (s) |
| --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| history-inventory | issue24-v1 | repopilot | SUCCEEDED | true | 9 | 40030 | 0.191448 | 0.191448 | 300.3503962329996 |

Results are raw development evidence; no performance numbers are prefilled.
