# GPT-5.6 Luna paired Agent smoke

On 2026-09-04, the pinned mini-SWE-agent baseline and RepoPilot each ran `seed-single-file` and `seed-cross-file`
with the same `gpt-5.6-luna` model, task snapshots, `python:3.12-slim` image, temperature, and Run Budget. All four
resulting Target Repositories passed the host-only hidden verifier.

| Task | Engine | Status | Passed | Steps | Tool Calls | Tokens | Cost | Duration | Errors |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| seed-single-file | baseline | Submitted | true | 5 | 5 | 9,052 | $0.00276892 | 37.54s | 1 |
| seed-single-file | RepoPilot | SUCCEEDED | true | 7 | 10 | 12,819 | $0.00280760 | 47.42s | 0 |
| seed-cross-file | baseline | Submitted | true | 9 | 11 | 24,326 | $0.00663492 | 113.43s | 3 |
| seed-cross-file | RepoPilot | BUDGET_EXCEEDED | true | 6 | 10 | 10,218 | $0.00274480 | 196.11s | 0 |

The baseline recovered from its recorded command failures. RepoPilot produced the same passing cross-file patch as
the baseline, but ended `BUDGET_EXCEEDED` because an in-flight model call crossed the 180-second wall-time budget
before it could cleanly finish. The four runs used 56,415 tokens and $0.01495624 in LiteLLM-calculated cost. These
costs are based on returned usage and LiteLLM's model price data, not intermediary invoice data. This is a paired
smoke test, not a performance ranking or a statistically meaningful success-rate comparison.
