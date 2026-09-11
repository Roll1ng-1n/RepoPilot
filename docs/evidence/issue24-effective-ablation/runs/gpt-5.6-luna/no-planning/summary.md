# Stage 4 evaluation

| Model | Engine | Group | Task pass | Successful termination | Recovery | LLM calls / solved | Tokens / solved | Tool failures / solved | Post-solution churn |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| openai/gpt-5.6-luna | repopilot | capability:recovery | 0/1 (0 unavailable) | 0.000 | 0.000 | unsupported | unsupported | unsupported | unsupported |
| openai/gpt-5.6-luna | repopilot | category:cross-file | 1/1 (0 unavailable) | 1.000 | unsupported | 5.000 | 15031.000 | 0.000 | unsupported |
| openai/gpt-5.6-luna | repopilot | category:recovery | 0/1 (0 unavailable) | 0.000 | 0.000 | unsupported | unsupported | unsupported | unsupported |
| openai/gpt-5.6-luna | repopilot | overall:all | 1/2 (0 unavailable) | 0.500 | 0.000 | 53.000 | 164894.000 | 20.000 | unsupported |

Cost per solved includes failed trials. Missing usage makes the corresponding total unavailable.
Compare tokens only within the same model. Detailed distributions and paired counts are in summary.json.

| Model | Category | Left | Right | Both | Left only | Right only | Neither | Unavailable |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |

# Agent Benchmark Summary

| Task | Snapshot Revision | Engine | Status | Success | Steps | Total tokens | Provider/LiteLLM cost | OpenAI Standard estimate | Duration (s) |
| --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| profile-ledger | issue24-v1 | repopilot | SUCCEEDED | true | 5 | 15031 | 0.0030531199999999994 | 0.00305312 | 81.19919846300036 |
| history-inventory | issue24-v1 | repopilot | BUDGET_EXCEEDED | false | 48 | 149863 | 0.03821592 | 0.03821592000000001 | 1390.9064433489984 |

Results are raw development evidence; no performance numbers are prefilled.
