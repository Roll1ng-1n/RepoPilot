# Stage 4 evaluation

| Model | Engine | Group | Task pass | Successful termination | Recovery | LLM calls / solved | Tokens / solved | Tool failures / solved | Post-solution churn |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| openai/gpt-5.6-sol | repopilot | capability:recovery | 1/1 (0 unavailable) | 1.000 | 1.000 | 8.000 | 14755.000 | 1.000 | unsupported |
| openai/gpt-5.6-sol | repopilot | category:recovery | 1/1 (0 unavailable) | 1.000 | 1.000 | 8.000 | 14755.000 | 1.000 | unsupported |
| openai/gpt-5.6-sol | repopilot | category:simple | 1/1 (0 unavailable) | 1.000 | unsupported | 8.000 | 20404.000 | 0.000 | unsupported |
| openai/gpt-5.6-sol | repopilot | overall:all | 2/2 (0 unavailable) | 1.000 | 1.000 | 8.000 | 17579.500 | 0.500 | unsupported |

Cost per solved includes failed trials. Missing usage makes the corresponding total unavailable.
Compare tokens only within the same model. Detailed distributions and paired counts are in summary.json.

| Model | Category | Left | Right | Both | Left only | Right only | Neither | Unavailable |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |

# Agent Benchmark Summary

| Task | Snapshot Revision | Engine | Status | Success | Steps | Total tokens | Provider/LiteLLM cost | OpenAI Standard estimate | Duration (s) |
| --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| seed-single-file | seed-v1 | repopilot | SUCCEEDED | true | 8 | 20404 | 0.070752 | 0.070752 | 36.99927002600009 |
| recovery-public-failure | recovery-v1 | repopilot | SUCCEEDED | true | 8 | 14755 | 0.0659704 | 0.0659704 | 101.73176507999995 |

Results are raw development evidence; no performance numbers are prefilled.
