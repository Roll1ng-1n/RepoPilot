# Stage 4 evaluation

| Model | Engine | Group | Task pass | Successful termination | Recovery | LLM calls / solved | Tokens / solved | Tool failures / solved | Post-solution churn |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| openai/gpt-5.6-luna | baseline | capability:recovery | 0/1 (0 unavailable) | 0.000 | unsupported | unsupported | unsupported | unsupported | unsupported |
| openai/gpt-5.6-luna | baseline | category:recovery | 0/1 (0 unavailable) | 0.000 | unsupported | unsupported | unsupported | unsupported | unsupported |
| openai/gpt-5.6-luna | baseline | category:simple | 0/1 (0 unavailable) | 0.000 | unsupported | unsupported | unsupported | unsupported | unsupported |
| openai/gpt-5.6-luna | baseline | overall:all | 0/2 (0 unavailable) | 0.000 | unsupported | unsupported | unsupported | unsupported | unsupported |
| openai/gpt-5.6-luna | repopilot | capability:recovery | 0/1 (0 unavailable) | 0.000 | unsupported | unsupported | unsupported | unsupported | unsupported |
| openai/gpt-5.6-luna | repopilot | category:recovery | 0/1 (0 unavailable) | 0.000 | unsupported | unsupported | unsupported | unsupported | unsupported |
| openai/gpt-5.6-luna | repopilot | category:simple | 0/1 (0 unavailable) | 0.000 | unsupported | unsupported | unsupported | unsupported | unsupported |
| openai/gpt-5.6-luna | repopilot | overall:all | 0/2 (0 unavailable) | 0.000 | unsupported | unsupported | unsupported | unsupported | unsupported |

Cost per solved includes failed trials. Missing usage makes the corresponding total unavailable.
Compare tokens only within the same model. Detailed distributions and paired counts are in summary.json.

| Model | Category | Left | Right | Both | Left only | Right only | Neither | Unavailable |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| openai/gpt-5.6-luna | all | baseline | repopilot | 0 | 0 | 0 | 2 | 0 |
| openai/gpt-5.6-luna | recovery | baseline | repopilot | 0 | 0 | 0 | 1 | 0 |
| openai/gpt-5.6-luna | simple | baseline | repopilot | 0 | 0 | 0 | 1 | 0 |

# Agent Benchmark Summary

| Task | Snapshot Revision | Engine | Status | Success | Steps | Total tokens | Provider/LiteLLM cost | OpenAI Standard estimate | Duration (s) |
| --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| seed-single-file | seed-v1 | baseline | UnsupportedParamsError | false | 1 | null | null | null | 0.02122511199922883 |
| seed-single-file | seed-v1 | repopilot | FAILED | false | 1 | null | null | null | 0.3683727940006065 |
| recovery-public-failure | recovery-v1 | baseline | UnsupportedParamsError | false | 1 | null | null | null | 0.006638942999416031 |
| recovery-public-failure | recovery-v1 | repopilot | FAILED | false | 1 | null | null | null | 0.32642754100015736 |

Results are raw development evidence; no performance numbers are prefilled.
