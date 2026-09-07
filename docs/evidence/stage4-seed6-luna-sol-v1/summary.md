# Stage 4 six-seed-task paired benchmark (Luna and Sol)

On 2026-09-06, the pinned mini-SWE-agent baseline and RepoPilot each ran the six
Stage 4 seed tasks with `gpt-5.6-luna` and `gpt-5.6-sol`, three rounds per
model. This evidence covers `6 tasks × 2 models × 3 rounds × 2 engines = 72`
Agent samples. It is the clean rerun of a batch whose first execution was
invalidated by a local proxy outage (recorded as connection errors, not as
model or engine results); this evidence is the retained clean dataset.

## Frozen configuration

- Fixed Git-enabled benchmark image `repopilot-benchmark:py312-git`
  (`repopilot-benchmark@sha256:29c73ce6d8fc5dde787d42327bbfdc1b64466e247935ea498efd6784890a0bc9`).
  Stage 0 preflight inside that image passed for `python` (3.12.14) and `git`
  (2.47.3) before every model-backed trial.
- Models: `gpt-5.6-luna` and `gpt-5.6-sol` via the OpenAI-compatible
  intermediary. Credential-free summary only; endpoint and key are not
  retained here.
- Shared run budget for both engines: 15 steps, one Replan, two consecutive
  failures, 30-second command timeout, 180-second Agent wall-clock budget.
  Each task manifest also declares its own `run_budget` (recorded per trial);
  the effective Agent budget is the shared invocation budget capped by
  `task.timeout_seconds`, which is 180 seconds for all six seed tasks.
- `temperature=0`, container proxy mode `none` (direct connection).
- One clean 12-sample run of `seed-single-file` plus one clean 60-sample run of
  the other five tasks; no batch errors and no connection errors in either.

## Results

### Model and engine aggregates

| Model | Engine | Samples | repo pass | task true | task false | task null | Statuses | Tokens | Provider/LiteLLM cost | OpenAI Standard estimate | Agent duration |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: | ---: |
| `gpt-5.6-luna` | baseline | 18 | 17 | 8 | 4 | 6 | Submitted ×17; TimeExceeded ×1 | 288,564 | $0.070230 | $0.070230 | 1,426.54 s |
| `gpt-5.6-luna` | RepoPilot | 18 | 18 | 11 | 2 | 5 | SUCCEEDED ×13; BUDGET_EXCEEDED ×5 | 750,527 | $0.125004 | $0.125004 | 2,269.11 s |
| `gpt-5.6-sol` | baseline | 18 | 18 | 7 | 5 | 6 | Submitted ×17; TimeExceeded ×1 | 314,091 | $1.845913 | $1.404204 | 1,532.28 s |
| `gpt-5.6-sol` | RepoPilot | 18 | 14 | 8 | 5 | 5 | SUCCEEDED ×12; BUDGET_EXCEEDED ×6 | 601,079 | $2.622835 | $2.089792 | 2,841.94 s |
| Total | | 72 | 67 | 34 | 16 | 22 | | 1,954,261 | $4.663981 | $3.689229 | 8,069.87 s |

`task_pass` is the three-valued AND of the hidden repository verifier and the
objective behavior checks. `task null` means evidence could not establish a
required behavior check; it is not a pass. The six null-heavy rows come from
the HITL and long-horizon seed tasks whose complete approval/budget audit is
unsupported by the current harness.

### Paired task outcomes (three rounds combined per model)

| Model | Both pass | Baseline only | RepoPilot only | Neither | Unavailable/null |
| --- | ---: | ---: | ---: | ---: | ---: |
| `gpt-5.6-luna` | 3 | 0 | 1 | 0 | 2 |
| `gpt-5.6-sol` | 2 | 1 | 1 | 0 | 2 |

Both engines passed `seed-single-file` and `seed-cross-file` in every round for
both models. Differences over the remaining tasks:

- `recovery-public-failure`: RepoPilot-only on Luna (4/3 resolved vs baseline);
  baseline-only on Sol.
- `replan-new-evidence`: both passed on Luna; RepoPilot-only on Sol.
- `workflow-long-chain` and `workflow-human-approval-git` are mostly `task null`
  because the harness cannot yet audit the complete execution-budget or
  approval behavior those tasks require; repository-only passes are retained
  separately in `summary.json`.

## Interpretation and limitations

- RepoPilot again shows a recurring `BUDGET_EXCEEDED` status while still
  producing correct repositories (for example Sol round-2 `replan-new-evidence`
  ended `BUDGET_EXCEEDED` with `task_pass=true`). Intermediary long-tail
  latency lets an in-flight model request return after the fixed 180-second
  wall clock, so agent status and final repository correctness must stay
  separate metrics.
- Baseline never reports native Replan/budget enforcement, so equal
  configuration must not be read as equal enforcement.
- Cost columns are per-provider LiteLLM cost and the separately labelled OpenAI
  Standard price estimate computed only from returned usage. They are not an
  intermediary invoice and are not pooled across models for ranking.
- These are three development rounds on six small fixed tasks with two models:
  calibration evidence, not a win rate, a stability claim, or a general
  performance result.

## Retained evidence

- Machine-readable aggregated data and all 72 trial rows:
  [summary.json](summary.json) (credential-free).
- Raw campaign output lives outside the repository under the local state
  directory (`campaigns/`); per-trial patches, traces, verifier output and
  workspace Git state are retained there. No API key, endpoint or proxy URL is
  stored in this evidence directory.
