# Stage 4 evaluation

| Model | Engine | Group | Task pass | Successful termination | Recovery | LLM calls / solved | Tokens / solved | Tool failures / solved | Post-solution churn |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| openai/gpt-5.6-luna | repopilot | capability:recovery | 1/1 (0 unavailable) | 0.000 | 1.000 | 7.000 | 6562.000 | 1.000 | unsupported |
| openai/gpt-5.6-luna | repopilot | category:recovery | 1/1 (0 unavailable) | 0.000 | 1.000 | 7.000 | 6562.000 | 1.000 | unsupported |
| openai/gpt-5.6-luna | repopilot | category:simple | 1/1 (0 unavailable) | 0.000 | unsupported | 8.000 | 16283.000 | 0.000 | unsupported |
| openai/gpt-5.6-luna | repopilot | overall:all | 2/2 (0 unavailable) | 0.000 | 1.000 | 7.500 | 11422.500 | 0.500 | unsupported |

Cost per solved includes failed trials. Missing usage makes the corresponding total unavailable.
Compare tokens only within the same model. Detailed distributions and paired counts are in summary.json.

| Model | Category | Left | Right | Both | Left only | Right only | Neither | Unavailable |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |

# Agent Benchmark Summary

| Task | Snapshot Revision | Engine | Status | Success | Steps | Total tokens | Provider/LiteLLM cost | OpenAI Standard estimate | Duration (s) |
| --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| seed-single-file | seed-v1 | repopilot | BUDGET_EXCEEDED | true | 8 | 16283 | 0.0037493200000000004 | 0.00374932 | 180.3694841800001 |
| recovery-public-failure | recovery-v1 | repopilot | BUDGET_EXCEEDED | true | 7 | 6562 | 0.0012314399999999999 | 0.00123144 | 180.58649211800014 |

Results are raw development evidence; no performance numbers are prefilled.
