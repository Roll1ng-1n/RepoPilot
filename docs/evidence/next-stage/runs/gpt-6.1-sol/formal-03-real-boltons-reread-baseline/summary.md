# Stage 4 evaluation

| Model | Engine | Group | Task pass | Successful termination | Recovery | LLM calls / solved | Tokens / solved | Tool failures / solved | Post-solution churn |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| openai/gpt-6.1-sol | baseline | category:simple | 1/1 (0 unavailable) | 1.000 | unsupported | 11.000 | 108900.000 | 2.000 | unsupported |
| openai/gpt-6.1-sol | baseline | overall:all | 1/1 (0 unavailable) | 1.000 | unsupported | 11.000 | 108900.000 | 2.000 | unsupported |

Cost per solved includes failed trials. Missing usage makes the corresponding total unavailable.
Compare tokens only within the same model. Detailed distributions and paired counts are in summary.json.

| Model | Category | Left | Right | Both | Left only | Right only | Neither | Unavailable |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |

# Agent Benchmark Summary

| Task | Snapshot Revision | Engine | Status | Success | Steps | Total tokens | Provider/LiteLLM cost | OpenAI Standard estimate | Duration (s) |
| --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| real-boltons-reread | c23dbdadb6fecdf505eb4231559561913b84c13f | baseline | Submitted | true | 11 | 108900 | 0.0621488 | null | 86.40402772800007 |

Results are raw development evidence; no performance numbers are prefilled.
