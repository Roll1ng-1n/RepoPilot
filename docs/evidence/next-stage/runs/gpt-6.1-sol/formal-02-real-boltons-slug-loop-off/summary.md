# Stage 4 evaluation

| Model | Engine | Group | Task pass | Successful termination | Recovery | LLM calls / solved | Tokens / solved | Tool failures / solved | Post-solution churn |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| openai/gpt-6.1-sol | repopilot | category:simple | 1/1 (0 unavailable) | 0.000 | unsupported | 6.000 | 49589.000 | 0.000 | unsupported |
| openai/gpt-6.1-sol | repopilot | overall:all | 1/1 (0 unavailable) | 0.000 | unsupported | 6.000 | 49589.000 | 0.000 | unsupported |

Cost per solved includes failed trials. Missing usage makes the corresponding total unavailable.
Compare tokens only within the same model. Detailed distributions and paired counts are in summary.json.

| Model | Category | Left | Right | Both | Left only | Right only | Neither | Unavailable |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |

# Agent Benchmark Summary

| Task | Snapshot Revision | Engine | Status | Success | Steps | Total tokens | Provider/LiteLLM cost | OpenAI Standard estimate | Duration (s) |
| --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| real-boltons-slug | c23dbdadb6fecdf505eb4231559561913b84c13f | repopilot | BUDGET_EXCEEDED | true | 7 | 49589 | 0.0376468 | null | 100.62364210499982 |

Results are raw development evidence; no performance numbers are prefilled.
