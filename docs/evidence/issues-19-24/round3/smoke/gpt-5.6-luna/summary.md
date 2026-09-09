# Stage 4 evaluation

| Model | Engine | Group | Task pass | Successful termination | Recovery | LLM calls / solved | Tokens / solved | Tool failures / solved | Post-solution churn |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| openai/gpt-5.6-luna | baseline | capability:recovery | 1/1 (0 unavailable) | 1.000 | 1.000 | 7.000 | 13702.000 | 1.000 | unsupported |
| openai/gpt-5.6-luna | baseline | category:recovery | 1/1 (0 unavailable) | 1.000 | 1.000 | 7.000 | 13702.000 | 1.000 | unsupported |
| openai/gpt-5.6-luna | baseline | category:simple | 1/1 (0 unavailable) | 1.000 | unsupported | 6.000 | 11789.000 | 0.000 | unsupported |
| openai/gpt-5.6-luna | baseline | overall:all | 2/2 (0 unavailable) | 1.000 | 1.000 | 6.500 | 12745.500 | 0.500 | unsupported |
| openai/gpt-5.6-luna | repopilot | capability:recovery | 1/1 (0 unavailable) | 0.000 | 1.000 | 14.000 | 68851.000 | 2.000 | unsupported |
| openai/gpt-5.6-luna | repopilot | category:recovery | 1/1 (0 unavailable) | 0.000 | 1.000 | 14.000 | 68851.000 | 2.000 | unsupported |
| openai/gpt-5.6-luna | repopilot | category:simple | 1/1 (0 unavailable) | 1.000 | unsupported | 8.000 | 18200.000 | 0.000 | unsupported |
| openai/gpt-5.6-luna | repopilot | overall:all | 2/2 (0 unavailable) | 0.500 | 1.000 | 11.000 | 43525.500 | 1.000 | unsupported |

Cost per solved includes failed trials. Missing usage makes the corresponding total unavailable.
Compare tokens only within the same model. Detailed distributions and paired counts are in summary.json.

| Model | Category | Left | Right | Both | Left only | Right only | Neither | Unavailable |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| openai/gpt-5.6-luna | all | baseline | repopilot | 2 | 0 | 0 | 0 | 0 |
| openai/gpt-5.6-luna | recovery | baseline | repopilot | 1 | 0 | 0 | 0 | 0 |
| openai/gpt-5.6-luna | simple | baseline | repopilot | 1 | 0 | 0 | 0 | 0 |

# Agent Benchmark Summary

| Task | Snapshot Revision | Engine | Status | Success | Steps | Total tokens | Provider/LiteLLM cost | OpenAI Standard estimate | Duration (s) |
| --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| seed-single-file | seed-v1 | baseline | Submitted | true | 6 | 11789 | 0.00311084 | 0.00311084 | 107.667240198 |
| seed-single-file | seed-v1 | repopilot | SUCCEEDED | true | 8 | 18200 | 0.00430652 | 0.00430652 | 95.87468966800003 |
| recovery-public-failure | recovery-v1 | baseline | Submitted | true | 7 | 13702 | 0.00363092 | 0.00363092 | 96.18043030500007 |
| recovery-public-failure | recovery-v1 | repopilot | BUDGET_EXCEEDED | true | 14 | 68851 | 0.01021772 | 0.01021772 | 180.40481660399996 |

Results are raw development evidence; no performance numbers are prefilled.
