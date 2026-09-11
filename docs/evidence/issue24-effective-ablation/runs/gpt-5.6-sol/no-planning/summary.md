# Stage 4 evaluation

| Model | Engine | Group | Task pass | Successful termination | Recovery | LLM calls / solved | Tokens / solved | Tool failures / solved | Post-solution churn |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| openai/gpt-5.6-sol | repopilot | capability:recovery | 0/1 (0 unavailable) | 0.000 | 0.000 | unsupported | unsupported | unsupported | unsupported |
| openai/gpt-5.6-sol | repopilot | category:cross-file | 1/1 (0 unavailable) | 1.000 | unsupported | 10.000 | 41486.000 | 1.000 | unsupported |
| openai/gpt-5.6-sol | repopilot | category:recovery | 0/1 (0 unavailable) | 0.000 | 0.000 | unsupported | unsupported | unsupported | unsupported |
| openai/gpt-5.6-sol | repopilot | overall:all | 1/2 (0 unavailable) | 0.500 | 0.000 | 25.000 | 78579.000 | 2.000 | unsupported |

Cost per solved includes failed trials. Missing usage makes the corresponding total unavailable.
Compare tokens only within the same model. Detailed distributions and paired counts are in summary.json.

| Model | Category | Left | Right | Both | Left only | Right only | Neither | Unavailable |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |

# Agent Benchmark Summary

| Task | Snapshot Revision | Engine | Status | Success | Steps | Total tokens | Provider/LiteLLM cost | OpenAI Standard estimate | Duration (s) |
| --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| profile-ledger | issue24-v1 | repopilot | SUCCEEDED | true | 10 | 41486 | 0.1411804 | 0.14118039999999998 | 901.2661902899999 |
| history-inventory | issue24-v1 | repopilot | FAILED | false | 15 | 37093 | 0.15266000000000002 | 0.15266 | 785.1467024750018 |

Results are raw development evidence; no performance numbers are prefilled.
