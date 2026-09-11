# Stage 4 evaluation

| Model | Engine | Group | Task pass | Successful termination | Recovery | LLM calls / solved | Tokens / solved | Tool failures / solved | Post-solution churn |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| openai/gpt-5.6-sol | repopilot | capability:recovery | 0/1 (0 unavailable) | 0.000 | 0.000 | unsupported | unsupported | unsupported | unsupported |
| openai/gpt-5.6-sol | repopilot | category:cross-file | 1/1 (0 unavailable) | 0.000 | unsupported | 6.000 | 23901.000 | 0.000 | unsupported |
| openai/gpt-5.6-sol | repopilot | category:recovery | 0/1 (0 unavailable) | 0.000 | 0.000 | unsupported | unsupported | unsupported | unsupported |
| openai/gpt-5.6-sol | repopilot | overall:all | 1/2 (0 unavailable) | 0.000 | 0.000 | 10.000 | 50714.000 | 1.000 | unsupported |

Cost per solved includes failed trials. Missing usage makes the corresponding total unavailable.
Compare tokens only within the same model. Detailed distributions and paired counts are in summary.json.

| Model | Category | Left | Right | Both | Left only | Right only | Neither | Unavailable |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |

# Agent Benchmark Summary

| Task | Snapshot Revision | Engine | Status | Success | Steps | Total tokens | Provider/LiteLLM cost | OpenAI Standard estimate | Duration (s) |
| --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| profile-ledger | issue24-v1 | repopilot | BUDGET_EXCEEDED | true | 7 | 23901 | 0.11299600000000001 | 0.112996 | 89.387934503 |
| history-inventory | issue24-v1 | repopilot | BUDGET_EXCEEDED | false | 5 | 26813 | 0.0986312 | 0.0986312 | 50.21417556599772 |

Results are raw development evidence; no performance numbers are prefilled.
