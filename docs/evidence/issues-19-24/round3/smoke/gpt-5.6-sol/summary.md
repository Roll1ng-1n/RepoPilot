# Stage 4 evaluation

| Model | Engine | Group | Task pass | Successful termination | Recovery | LLM calls / solved | Tokens / solved | Tool failures / solved | Post-solution churn |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| openai/gpt-5.6-sol | baseline | capability:recovery | 0/1 (0 unavailable) | 1.000 | unsupported | unsupported | unsupported | unsupported | unsupported |
| openai/gpt-5.6-sol | baseline | category:recovery | 0/1 (0 unavailable) | 1.000 | unsupported | unsupported | unsupported | unsupported | unsupported |
| openai/gpt-5.6-sol | baseline | category:simple | 1/1 (0 unavailable) | 1.000 | unsupported | 5.000 | 9128.000 | 0.000 | unsupported |
| openai/gpt-5.6-sol | baseline | overall:all | 1/2 (0 unavailable) | 1.000 | unsupported | 11.000 | 49801.000 | 2.000 | unsupported |
| openai/gpt-5.6-sol | repopilot | capability:recovery | 1/1 (0 unavailable) | 0.000 | 1.000 | 8.000 | 49520.000 | 1.000 | unsupported |
| openai/gpt-5.6-sol | repopilot | category:recovery | 1/1 (0 unavailable) | 0.000 | 1.000 | 8.000 | 49520.000 | 1.000 | unsupported |
| openai/gpt-5.6-sol | repopilot | category:simple | 1/1 (0 unavailable) | 1.000 | unsupported | 11.000 | 24996.000 | 0.000 | unsupported |
| openai/gpt-5.6-sol | repopilot | overall:all | 2/2 (0 unavailable) | 0.500 | 1.000 | 9.500 | 37258.000 | 0.500 | unsupported |

Cost per solved includes failed trials. Missing usage makes the corresponding total unavailable.
Compare tokens only within the same model. Detailed distributions and paired counts are in summary.json.

| Model | Category | Left | Right | Both | Left only | Right only | Neither | Unavailable |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| openai/gpt-5.6-sol | all | baseline | repopilot | 1 | 0 | 1 | 0 | 0 |
| openai/gpt-5.6-sol | recovery | baseline | repopilot | 0 | 0 | 1 | 0 | 0 |
| openai/gpt-5.6-sol | simple | baseline | repopilot | 1 | 0 | 0 | 0 | 0 |

# Agent Benchmark Summary

| Task | Snapshot Revision | Engine | Status | Success | Steps | Total tokens | Provider/LiteLLM cost | OpenAI Standard estimate | Duration (s) |
| --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| seed-single-file | seed-v1 | baseline | Submitted | true | 5 | 9128 | 0.0496864 | 0.0496864 | 82.897062987 |
| seed-single-file | seed-v1 | repopilot | SUCCEEDED | true | 11 | 24996 | 0.0758976 | 0.07589760000000001 | 157.969051186 |
| recovery-public-failure | recovery-v1 | baseline | Submitted | true | 6 | 40673 | 0.151268 | 0.151268 | 114.04197266799997 |
| recovery-public-failure | recovery-v1 | repopilot | BUDGET_EXCEEDED | true | 8 | 49520 | 0.11254720000000001 | 0.1125472 | 180.41229219800005 |

Results are raw development evidence; no performance numbers are prefilled.
