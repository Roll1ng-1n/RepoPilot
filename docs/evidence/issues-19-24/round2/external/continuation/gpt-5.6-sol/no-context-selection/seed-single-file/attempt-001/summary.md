# Stage 4 evaluation

| Model | Engine | Group | Task pass | Successful termination | Recovery | LLM calls / solved | Tokens / solved | Tool failures / solved | Post-solution churn |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| openai/gpt-5.6-sol | repopilot | category:simple | 0/1 (0 unavailable) | 0.000 | unsupported | unsupported | unsupported | unsupported | unsupported |
| openai/gpt-5.6-sol | repopilot | overall:all | 0/1 (0 unavailable) | 0.000 | unsupported | unsupported | unsupported | unsupported | unsupported |

Cost per solved includes failed trials. Missing usage makes the corresponding total unavailable.
Compare tokens only within the same model. Detailed distributions and paired counts are in summary.json.

| Model | Category | Left | Right | Both | Left only | Right only | Neither | Unavailable |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |

# Agent Benchmark Summary

| Task | Snapshot Revision | Engine | Status | Success | Steps | Total tokens | Provider/LiteLLM cost | OpenAI Standard estimate | Duration (s) |
| --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| seed-single-file | seed-v1 | repopilot | BUDGET_EXCEEDED | false | 9 | 28794 | 0.09843999999999999 | 0.09844 | 180.3545529230032 |

Results are raw development evidence; no performance numbers are prefilled.
