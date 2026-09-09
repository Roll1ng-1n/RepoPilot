# Stage 4 evaluation

| Model | Engine | Group | Task pass | Successful termination | Recovery | LLM calls / solved | Tokens / solved | Tool failures / solved | Post-solution churn |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| openai/gpt-5.6-sol | baseline | capability:recovery | 0/1 (0 unavailable) | 0.000 | unsupported | unsupported | unsupported | unsupported | unsupported |
| openai/gpt-5.6-sol | baseline | category:recovery | 0/1 (0 unavailable) | 0.000 | unsupported | unsupported | unsupported | unsupported | unsupported |
| openai/gpt-5.6-sol | baseline | category:simple | 0/1 (0 unavailable) | 0.000 | unsupported | unsupported | unsupported | unsupported | unsupported |
| openai/gpt-5.6-sol | baseline | overall:all | 0/2 (0 unavailable) | 0.000 | unsupported | unsupported | unsupported | unsupported | unsupported |
| openai/gpt-5.6-sol | repopilot | capability:recovery | 0/1 (0 unavailable) | 0.000 | 0.000 | unsupported | unsupported | unsupported | unsupported |
| openai/gpt-5.6-sol | repopilot | category:recovery | 0/1 (0 unavailable) | 0.000 | 0.000 | unsupported | unsupported | unsupported | unsupported |
| openai/gpt-5.6-sol | repopilot | category:simple | 0/1 (0 unavailable) | 0.000 | unsupported | unsupported | unsupported | unsupported | unsupported |
| openai/gpt-5.6-sol | repopilot | overall:all | 0/2 (0 unavailable) | 0.000 | 0.000 | unsupported | unsupported | unsupported | unsupported |

Cost per solved includes failed trials. Missing usage makes the corresponding total unavailable.
Compare tokens only within the same model. Detailed distributions and paired counts are in summary.json.

| Model | Category | Left | Right | Both | Left only | Right only | Neither | Unavailable |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| openai/gpt-5.6-sol | all | baseline | repopilot | 0 | 0 | 0 | 2 | 0 |
| openai/gpt-5.6-sol | recovery | baseline | repopilot | 0 | 0 | 0 | 1 | 0 |
| openai/gpt-5.6-sol | simple | baseline | repopilot | 0 | 0 | 0 | 1 | 0 |

# Agent Benchmark Summary

| Task | Snapshot Revision | Engine | Status | Success | Steps | Total tokens | Provider/LiteLLM cost | OpenAI Standard estimate | Duration (s) |
| --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| seed-single-file | seed-v1 | baseline | TimeExceeded | false | 3 | 4590 | 0.033288 | 0.033288 | 223.00229647000015 |
| seed-single-file | seed-v1 | repopilot | BUDGET_EXCEEDED | false | 6 | 11106 | 0.053655999999999995 | 0.053656 | 90.25540299500062 |
| recovery-public-failure | recovery-v1 | baseline | TimeExceeded | false | 3 | 3429 | 0.021060000000000002 | 0.02106 | 203.72789651499988 |
| recovery-public-failure | recovery-v1 | repopilot | BUDGET_EXCEEDED | false | 6 | 4499 | 0.020859999999999997 | 0.02086 | 180.35301400900062 |

Results are raw development evidence; no performance numbers are prefilled.
