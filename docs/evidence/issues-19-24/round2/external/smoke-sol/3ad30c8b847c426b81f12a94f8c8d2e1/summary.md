# Stage 4 evaluation

| Model | Engine | Group | Task pass | Successful termination | Recovery | LLM calls / solved | Tokens / solved | Tool failures / solved | Post-solution churn |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| openai/gpt-5.6-sol | baseline | capability:recovery | 0/1 (0 unavailable) | 0.000 | unsupported | unsupported | unsupported | unsupported | unsupported |
| openai/gpt-5.6-sol | baseline | category:recovery | 0/1 (0 unavailable) | 0.000 | unsupported | unsupported | unsupported | unsupported | unsupported |
| openai/gpt-5.6-sol | baseline | category:simple | 0/1 (0 unavailable) | 0.000 | unsupported | unsupported | unsupported | unsupported | unsupported |
| openai/gpt-5.6-sol | baseline | overall:all | 0/2 (0 unavailable) | 0.000 | unsupported | unsupported | unsupported | unsupported | unsupported |
| openai/gpt-5.6-sol | repopilot | capability:recovery | 0/1 (0 unavailable) | 0.000 | unsupported | unsupported | unsupported | unsupported | unsupported |
| openai/gpt-5.6-sol | repopilot | category:recovery | 0/1 (0 unavailable) | 0.000 | unsupported | unsupported | unsupported | unsupported | unsupported |
| openai/gpt-5.6-sol | repopilot | category:simple | 0/1 (0 unavailable) | 0.000 | unsupported | unsupported | unsupported | unsupported | unsupported |
| openai/gpt-5.6-sol | repopilot | overall:all | 0/2 (0 unavailable) | 0.000 | unsupported | unsupported | unsupported | unsupported | unsupported |

Cost per solved includes failed trials. Missing usage makes the corresponding total unavailable.
Compare tokens only within the same model. Detailed distributions and paired counts are in summary.json.

| Model | Category | Left | Right | Both | Left only | Right only | Neither | Unavailable |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| openai/gpt-5.6-sol | all | baseline | repopilot | 0 | 0 | 0 | 2 | 0 |
| openai/gpt-5.6-sol | recovery | baseline | repopilot | 0 | 0 | 0 | 1 | 0 |
| openai/gpt-5.6-sol | simple | baseline | repopilot | 0 | 0 | 0 | 1 | 0 |

# Agent Benchmark Summary

| Task | Snapshot Revision | Engine | Status | Success | Steps | Total tokens | Provider/LiteLLM cost | OpenAI Standard estimate | Duration (s) |
| --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| seed-single-file | seed-v1 | baseline | UnsupportedParamsError | false | 1 | null | null | null | 0.03447615400000359 |
| seed-single-file | seed-v1 | repopilot | FAILED | false | 1 | null | null | null | 0.3529093479992298 |
| recovery-public-failure | recovery-v1 | baseline | UnsupportedParamsError | false | 1 | null | null | null | 0.00681276099930983 |
| recovery-public-failure | recovery-v1 | repopilot | FAILED | false | 1 | null | null | null | 0.3646687929976906 |

Results are raw development evidence; no performance numbers are prefilled.
