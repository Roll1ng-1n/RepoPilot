# Stage 4 evaluation

| Model | Engine | Group | Task pass | Successful termination | Recovery | LLM calls / solved | Tokens / solved | Tool failures / solved | Post-solution churn |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| openai/gpt-5.6-luna | repopilot | capability:recovery | 0/1 (0 unavailable) | 0.000 | 0.000 | unsupported | unsupported | unsupported | unsupported |
| openai/gpt-5.6-luna | repopilot | category:recovery | 0/1 (0 unavailable) | 0.000 | 0.000 | unsupported | unsupported | unsupported | unsupported |
| openai/gpt-5.6-luna | repopilot | category:simple | 0/1 (0 unavailable) | 0.000 | unsupported | unsupported | unsupported | unsupported | unsupported |
| openai/gpt-5.6-luna | repopilot | overall:all | 0/2 (0 unavailable) | 0.000 | 0.000 | unsupported | unsupported | unsupported | unsupported |

Cost per solved includes failed trials. Missing usage makes the corresponding total unavailable.
Compare tokens only within the same model. Detailed distributions and paired counts are in summary.json.

| Model | Category | Left | Right | Both | Left only | Right only | Neither | Unavailable |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |

# Agent Benchmark Summary

| Task | Snapshot Revision | Engine | Status | Success | Steps | Total tokens | Provider/LiteLLM cost | OpenAI Standard estimate | Duration (s) |
| --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| seed-single-file | seed-v1 | repopilot | FAILED | false | 2 | 1158 | 0.00025659999999999995 | 0.0002566 | 108.48828105099892 |
| recovery-public-failure | recovery-v1 | repopilot | FAILED | false | 2 | 2621 | 0.0006031999999999999 | 0.0006032 | 11.021471963002114 |

Results are raw development evidence; no performance numbers are prefilled.
