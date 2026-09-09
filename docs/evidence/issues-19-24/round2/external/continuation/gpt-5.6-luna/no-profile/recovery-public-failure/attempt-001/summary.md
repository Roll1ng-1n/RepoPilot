# Stage 4 evaluation

| Model | Engine | Group | Task pass | Successful termination | Recovery | LLM calls / solved | Tokens / solved | Tool failures / solved | Post-solution churn |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| openai/gpt-5.6-luna | repopilot | capability:recovery | 1/1 (0 unavailable) | 0.000 | 1.000 | 15.000 | 58777.000 | 6.000 | unsupported |
| openai/gpt-5.6-luna | repopilot | category:recovery | 1/1 (0 unavailable) | 0.000 | 1.000 | 15.000 | 58777.000 | 6.000 | unsupported |
| openai/gpt-5.6-luna | repopilot | overall:all | 1/1 (0 unavailable) | 0.000 | 1.000 | 15.000 | 58777.000 | 6.000 | unsupported |

Cost per solved includes failed trials. Missing usage makes the corresponding total unavailable.
Compare tokens only within the same model. Detailed distributions and paired counts are in summary.json.

| Model | Category | Left | Right | Both | Left only | Right only | Neither | Unavailable |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |

# Agent Benchmark Summary

| Task | Snapshot Revision | Engine | Status | Success | Steps | Total tokens | Provider/LiteLLM cost | OpenAI Standard estimate | Duration (s) |
| --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| recovery-public-failure | recovery-v1 | repopilot | BUDGET_EXCEEDED | true | 15 | 58777 | 0.008384079999999999 | 0.008384080000000002 | 112.20348504700087 |

Results are raw development evidence; no performance numbers are prefilled.
