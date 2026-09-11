# Stage 4 evaluation

| Model | Engine | Group | Task pass | Successful termination | Recovery | LLM calls / solved | Tokens / solved | Tool failures / solved | Post-solution churn |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| openai/gpt-5.6-luna | repopilot | category:cross-file | 1/1 (0 unavailable) | 1.000 | unsupported | 7.000 | 28021.000 | 0.000 | unsupported |
| openai/gpt-5.6-luna | repopilot | overall:all | 1/1 (0 unavailable) | 1.000 | unsupported | 7.000 | 28021.000 | 0.000 | unsupported |

Cost per solved includes failed trials. Missing usage makes the corresponding total unavailable.
Compare tokens only within the same model. Detailed distributions and paired counts are in summary.json.

| Model | Category | Left | Right | Both | Left only | Right only | Neither | Unavailable |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |

# Agent Benchmark Summary

| Task | Snapshot Revision | Engine | Status | Success | Steps | Total tokens | Provider/LiteLLM cost | OpenAI Standard estimate | Duration (s) |
| --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| profile-ledger | issue24-v1 | repopilot | SUCCEEDED | true | 7 | 28021 | 0.005440799999999999 | 0.0054408 | 163.28213572599634 |

Results are raw development evidence; no performance numbers are prefilled.
