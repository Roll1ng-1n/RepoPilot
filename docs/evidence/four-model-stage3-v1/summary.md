# Four-model Stage 3 paired benchmark

On 2026-09-05, the pinned mini-SWE-agent baseline and RepoPilot each ran six
fixed tasks with `gpt-5.6-sol`, `gpt-5.6-terra`, `gpt-5.6-luna`, and
`gpt-5.5`. The campaign used one round, `temperature=0`, the same
`python:3.12-slim` image, no Docker proxy, and the same Run Budget for both
engines: 15 steps, one Replan, two consecutive failures, 30-second command
timeouts, and a 180-second Agent wall-clock budget.

The campaign completed all 48 samples with no batch errors. In total, 32/48
Target Repositories passed their hidden verifier. The runs used 949,636 tokens
and had 8,017.82 seconds of summed Agent duration. The OpenAI Standard estimate
was $3.25369592. This is an estimate from returned usage and the official
pricing basis dated 2026-09-04, not intermediary invoice data.

## Model and engine results

| Model | Engine | Verifier pass | Statuses | Tokens | OpenAI estimate | Total / mean duration |
| --- | --- | ---: | --- | ---: | ---: | ---: |
| `gpt-5.6-sol` | baseline | 6/6 | Submitted ×6 | 120,573 | $0.52098000 | 543.62s / 90.60s |
| `gpt-5.6-sol` | RepoPilot | 4/6 | SUCCEEDED ×3; BUDGET_EXCEEDED ×3 | 128,852 | $0.46832000 | 1,139.50s / 189.92s |
| `gpt-5.6-terra` | baseline | 2/6 | Submitted ×2; TimeExceeded ×4 | 44,659 | $0.14163840 | 1,223.95s / 203.99s |
| `gpt-5.6-terra` | RepoPilot | 3/6 | SUCCEEDED ×3; BUDGET_EXCEEDED ×3 | 120,019 | $0.27827040 | 1,390.50s / 231.75s |
| `gpt-5.6-luna` | baseline | 3/6 | Submitted ×4; TimeExceeded ×2 | 93,090 | $0.02592044 | 927.85s / 154.64s |
| `gpt-5.6-luna` | RepoPilot | 4/6 | SUCCEEDED ×3; BUDGET_EXCEEDED ×3 | 94,807 | $0.02347668 | 1,493.90s / 248.98s |
| `gpt-5.5` | baseline | 5/6 | Submitted ×5; TimeExceeded ×1 | 122,336 | $0.83405600 | 771.99s / 128.66s |
| `gpt-5.5` | RepoPilot | 5/6 | SUCCEEDED ×5; BUDGET_EXCEEDED ×1 | 225,300 | $0.96103400 | 526.51s / 87.75s |

Across all models, baseline and RepoPilot both passed 16/24 samples. RepoPilot
used 568,978 tokens versus baseline's 380,658 (+49.5%), had an OpenAI estimate
of $1.73110108 versus $1.52259484 (+13.7%), and used 4,550.41 versus 3,467.41
summed Agent seconds (+31.2%). These are one-round development observations,
not stable rankings.

## Paired task outcomes

| Model | Both pass | Baseline only | RepoPilot only | Neither passes |
| --- | ---: | ---: | ---: | ---: |
| `gpt-5.6-sol` | 4 | 2 | 0 | 0 |
| `gpt-5.6-terra` | 1 | 1 | 2 | 2 |
| `gpt-5.6-luna` | 2 | 1 | 2 | 1 |
| `gpt-5.5` | 5 | 0 | 0 | 1 |
| Total | 12 | 4 | 4 | 4 |

The one-sided RepoPilot wins were Terra on `seed-cross-file` and
`recovery-public-failure`, plus Luna on `seed-single-file` and
`seed-cross-file`. The one-sided baseline wins were Sol on
`seed-single-file` and `workflow-human-approval-git`, Terra on
`replan-new-evidence`, and Luna on `workflow-human-approval-git`.

## Interpretation and limitation

- Three RepoPilot runs ended `BUDGET_EXCEEDED` but still passed the hidden
  verifier. Agent status and final repository correctness must therefore remain
  separate metrics.
- The intermediary produced severe long-tail latency. Several in-flight calls
  returned well after the fixed 180-second budget, with individual Agent runs
  reaching roughly 250–496 seconds. Stage 1 transport probes did not predict
  this multi-step behavior.
- The `python:3.12-slim` benchmark container did not contain the `git` binary.
  Every model encountered command exit code 127 on the
  `workflow-human-approval-git` task. Some baseline runs worked around the
  missing executable, but the task is environment-confounded and should not be
  used for an engine ranking until the benchmark image is fixed. Excluding this
  task post hoc, baseline passed 14/20 and RepoPilot passed 16/20; this
  sensitivity view is not the primary predeclared result.
- All 48 raw result, patch, trajectory/trace, and verifier artifacts were
  retained locally. The committed `summary.json` removes credentials,
  intermediary endpoint details, absolute artifact paths, and verbose model
  transcripts while preserving the measured fields and patch hashes.

This is a single round over small fixed tasks. Stage 4 is required before
making stability claims, and its benchmark image must include Git first.
