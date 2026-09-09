# Stage 4 evaluation

| Model | Engine | Group | Task pass | Successful termination | Recovery | LLM calls / solved | Tokens / solved | Tool failures / solved | Post-solution churn |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| openai/gpt-5.6-luna | baseline | capability:recovery | 0/1 (0 unavailable) | 1.000 | unsupported | unsupported | unsupported | unsupported | unsupported |
| openai/gpt-5.6-luna | baseline | category:recovery | 0/1 (0 unavailable) | 1.000 | unsupported | unsupported | unsupported | unsupported | unsupported |
| openai/gpt-5.6-luna | baseline | category:simple | 1/1 (0 unavailable) | 1.000 | unsupported | 6.000 | 10453.000 | 0.000 | unsupported |
| openai/gpt-5.6-luna | baseline | overall:all | 1/2 (0 unavailable) | 1.000 | unsupported | 13.000 | 27794.000 | 1.000 | unsupported |
| openai/gpt-5.6-luna | repopilot | capability:recovery | 0/1 (0 unavailable) | 0.000 | 0.000 | unsupported | unsupported | unsupported | unsupported |
| openai/gpt-5.6-luna | repopilot | category:recovery | 0/1 (0 unavailable) | 0.000 | 0.000 | unsupported | unsupported | unsupported | unsupported |
| openai/gpt-5.6-luna | repopilot | category:simple | 0/1 (0 unavailable) | 0.000 | unsupported | unsupported | unsupported | unsupported | unsupported |
| openai/gpt-5.6-luna | repopilot | overall:all | 0/2 (0 unavailable) | 0.000 | 0.000 | unsupported | unsupported | unsupported | unsupported |

Cost per solved includes failed trials. Missing usage makes the corresponding total unavailable.
Compare tokens only within the same model. Detailed distributions and paired counts are in summary.json.

| Model | Category | Left | Right | Both | Left only | Right only | Neither | Unavailable |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| openai/gpt-5.6-luna | all | baseline | repopilot | 0 | 1 | 0 | 1 | 0 |
| openai/gpt-5.6-luna | recovery | baseline | repopilot | 0 | 0 | 0 | 1 | 0 |
| openai/gpt-5.6-luna | simple | baseline | repopilot | 0 | 1 | 0 | 0 | 0 |

# Agent Benchmark Summary

| Task | Snapshot Revision | Engine | Status | Success | Steps | Total tokens | Provider/LiteLLM cost | OpenAI Standard estimate | Duration (s) |
| --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| seed-single-file | seed-v1 | baseline | Submitted | true | 6 | 10453 | 0.0035636 | 0.0035636 | 61.484942614999454 |
| seed-single-file | seed-v1 | repopilot | BUDGET_EXCEEDED | false | 7 | 11540 | 0.0025459999999999997 | 0.002546 | 180.33969103600248 |
| recovery-public-failure | recovery-v1 | baseline | Submitted | true | 7 | 17341 | 0.00375944 | 0.00375944 | 131.4473569460024 |
| recovery-public-failure | recovery-v1 | repopilot | BUDGET_EXCEEDED | false | 7 | 14703 | 0.0036885999999999993 | 0.0036885999999999998 | 116.96828193900001 |

Results are raw development evidence; no performance numbers are prefilled.
