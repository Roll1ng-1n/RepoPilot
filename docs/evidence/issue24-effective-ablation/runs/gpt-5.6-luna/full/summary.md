# Stage 4 evaluation

| Model | Engine | Group | Task pass | Successful termination | Recovery | LLM calls / solved | Tokens / solved | Tool failures / solved | Post-solution churn |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| openai/gpt-5.6-luna | baseline | capability:recovery | 0/1 (0 unavailable) | 1.000 | unsupported | unsupported | unsupported | unsupported | unsupported |
| openai/gpt-5.6-luna | baseline | category:cross-file | 1/1 (0 unavailable) | 1.000 | unsupported | 7.000 | 18448.000 | 1.000 | unsupported |
| openai/gpt-5.6-luna | baseline | category:recovery | 0/1 (0 unavailable) | 1.000 | unsupported | unsupported | unsupported | unsupported | unsupported |
| openai/gpt-5.6-luna | baseline | overall:all | 1/2 (0 unavailable) | 1.000 | unsupported | 12.000 | 62848.000 | 1.000 | unsupported |
| openai/gpt-5.6-luna | repopilot | capability:recovery | 0/1 (0 unavailable) | 0.000 | 0.000 | unsupported | unsupported | unsupported | unsupported |
| openai/gpt-5.6-luna | repopilot | category:cross-file | 1/1 (0 unavailable) | 1.000 | unsupported | 9.000 | 41771.000 | 0.000 | unsupported |
| openai/gpt-5.6-luna | repopilot | category:recovery | 0/1 (0 unavailable) | 0.000 | 0.000 | unsupported | unsupported | unsupported | unsupported |
| openai/gpt-5.6-luna | repopilot | overall:all | 1/2 (0 unavailable) | 0.500 | 0.000 | 57.000 | 204943.000 | 19.000 | unsupported |

Cost per solved includes failed trials. Missing usage makes the corresponding total unavailable.
Compare tokens only within the same model. Detailed distributions and paired counts are in summary.json.

| Model | Category | Left | Right | Both | Left only | Right only | Neither | Unavailable |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| openai/gpt-5.6-luna | all | baseline | repopilot | 1 | 0 | 0 | 1 | 0 |
| openai/gpt-5.6-luna | cross-file | baseline | repopilot | 1 | 0 | 0 | 0 | 0 |
| openai/gpt-5.6-luna | recovery | baseline | repopilot | 0 | 0 | 0 | 1 | 0 |

# Agent Benchmark Summary

| Task | Snapshot Revision | Engine | Status | Success | Steps | Total tokens | Provider/LiteLLM cost | OpenAI Standard estimate | Duration (s) |
| --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| profile-ledger | issue24-v1 | baseline | Submitted | true | 7 | 18448 | 0.00452284 | 0.00452284 | 177.7182346749978 |
| profile-ledger | issue24-v1 | repopilot | SUCCEEDED | true | 9 | 41771 | 0.008431280000000001 | 0.008431280000000001 | 55.918159347002074 |
| history-inventory | issue24-v1 | baseline | Submitted | true | 5 | 44400 | 0.008746319999999998 | 0.00874632 | 250.04185808900002 |
| history-inventory | issue24-v1 | repopilot | BUDGET_EXCEEDED | false | 48 | 163172 | 0.03526363999999999 | 0.03526364 | 772.8558982249997 |

Results are raw development evidence; no performance numbers are prefilled.
