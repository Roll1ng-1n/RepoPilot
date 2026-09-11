# Stage 4 evaluation

| Model | Engine | Group | Task pass | Successful termination | Recovery | LLM calls / solved | Tokens / solved | Tool failures / solved | Post-solution churn |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| openai/gpt-5.6-sol | baseline | capability:recovery | 0/1 (0 unavailable) | 1.000 | unsupported | unsupported | unsupported | unsupported | unsupported |
| openai/gpt-5.6-sol | baseline | category:cross-file | 1/1 (0 unavailable) | 1.000 | unsupported | 7.000 | 17469.000 | 0.000 | unsupported |
| openai/gpt-5.6-sol | baseline | category:recovery | 0/1 (0 unavailable) | 1.000 | unsupported | unsupported | unsupported | unsupported | unsupported |
| openai/gpt-5.6-sol | baseline | overall:all | 1/2 (0 unavailable) | 1.000 | unsupported | 14.000 | 92330.000 | 1.000 | unsupported |
| openai/gpt-5.6-sol | repopilot | capability:recovery | 0/1 (0 unavailable) | 0.000 | 0.000 | unsupported | unsupported | unsupported | unsupported |
| openai/gpt-5.6-sol | repopilot | category:cross-file | 1/1 (0 unavailable) | 1.000 | unsupported | 8.000 | 49552.000 | 0.000 | unsupported |
| openai/gpt-5.6-sol | repopilot | category:recovery | 0/1 (0 unavailable) | 0.000 | 0.000 | unsupported | unsupported | unsupported | unsupported |
| openai/gpt-5.6-sol | repopilot | overall:all | 1/2 (0 unavailable) | 0.500 | 0.000 | 56.000 | 207915.000 | 18.000 | unsupported |

Cost per solved includes failed trials. Missing usage makes the corresponding total unavailable.
Compare tokens only within the same model. Detailed distributions and paired counts are in summary.json.

| Model | Category | Left | Right | Both | Left only | Right only | Neither | Unavailable |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| openai/gpt-5.6-sol | all | baseline | repopilot | 1 | 0 | 0 | 1 | 0 |
| openai/gpt-5.6-sol | cross-file | baseline | repopilot | 1 | 0 | 0 | 0 | 0 |
| openai/gpt-5.6-sol | recovery | baseline | repopilot | 0 | 0 | 0 | 1 | 0 |

# Agent Benchmark Summary

| Task | Snapshot Revision | Engine | Status | Success | Steps | Total tokens | Provider/LiteLLM cost | OpenAI Standard estimate | Duration (s) |
| --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| profile-ledger | issue24-v1 | baseline | Submitted | true | 7 | 17469 | 0.0885128 | 0.0885128 | 209.02460079700177 |
| profile-ledger | issue24-v1 | repopilot | SUCCEEDED | true | 8 | 49552 | 0.165152 | 0.165152 | 268.8106533700011 |
| history-inventory | issue24-v1 | baseline | Submitted | true | 7 | 74861 | 0.242836 | 0.242836 | 113.1138971420005 |
| history-inventory | issue24-v1 | repopilot | BUDGET_EXCEEDED | false | 48 | 158363 | 0.7500567999999996 | 0.7500568000000001 | 542.0897665589982 |

Results are raw development evidence; no performance numbers are prefilled.
