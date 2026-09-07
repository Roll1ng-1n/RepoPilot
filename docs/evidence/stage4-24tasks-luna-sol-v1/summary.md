# Stage 4 remaining 24 tasks, Luna and Sol, three rounds

Run 2026-09-06 through 2026-09-07 on the fixed Git-enabled benchmark image.
`gpt-5.6-luna` and `gpt-5.6-sol` each ran the 24 Stage 4 tasks that extend the
six seed tasks already archived under `stage4-seed6-luna-sol-v1`, three rounds
per model, on both the pinned mini-SWE-agent baseline and RepoPilot:
`24 tasks × 2 models × 3 rounds × 2 engines = 288` Agent samples, zero batch
errors. Together with the six-seed evidence this covers the full Stage 4 suite
of 30 tasks for two models.

## Frozen configuration

- Fixed image `repopilot-benchmark:py312-git`
  (`repopilot-benchmark@sha256:29c73ce6d8fc5dde787d42327bbfdc1b64466e247935ea498efd6784890a0bc9`);
  Stage 0 preflight passed inside the image for `python` (3.12.14) and `git`
  (2.47.3) before every trial.
- Models via the OpenAI-compatible intermediary. Credential-free summary only;
  endpoint and key are not retained here. The account restricted requests to
  streaming, so both engine paths forced `stream=true` and re-aggregated chunks
  with `litellm.stream_chunk_builder` (RepoPilot: `repopilot.model.stream_or_plain_completion`;
  baseline: `repopilot.litellm_streaming.StreamingLitellmModel`). Non-streaming
  behavior is preserved when no account restriction is present.
- Effective budget per trial comes from each task manifest `run_budget`
  (24 steps / 240-second wall clock / three Replans / three consecutive
  failures), applied on top of the shared invocation budget and capped by the
  task timeout. Seed and long-horizon/HITL manifests differ deliberately.
- `temperature=0`, container proxy mode none (direct connection).

## Totals

| Metric | Value |
| --- | ---: |
| Samples | 288 |
| Batch errors | 0 |
| `task_pass` true / false / null | 121 / 127 / 40 |
| Repository verifier pass | 199 / 288 |
| Total tokens | 7,209,561 |
| Provider/LiteLLM cost | $29.72 |
| OpenAI Standard estimate | $22.51 |
| Agent duration | 48,672 s (≈ 13.5 h wall) |
| Environmental-error reruns | 3 |

Three baseline trials were replaced after the fact by a rerun in a fresh output
root: two Luna round-1 `InternalServerError`s caused by the local network
outage of 2026-09-06, and one Sol round-1 upstream `BadRequestError`. The
original failure records remain in the campaign artifacts and are marked
`rerun_replacement` in `summary.json`.

Six `FAILED` trials (all `MODEL_ERROR`, malformed or truncated tool-call JSON
from the model/intermediary, including a 213k-char truncated response) and four
HITL trials (`UNVERIFIED` ×3 and one `WAITING_FOR_APPROVAL`) are retained as
evidence without rerun: the former because RepoPilot classifies them as
non-transient, the latter because the full approval/budget audit is
unsupported. Neither is counted as a model win; both remain visible per sample.

## Aggregates

| Model | Engine | Samples | repo pass | task true | task false | task null | Provider cost | Duration |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `gpt-5.6-luna` | baseline | 72 | 53 | 27 | 36 | 9 | $0.28 | 14,343 s |
| `gpt-5.6-luna` | RepoPilot | 72 | 33 | 21 | 45 | 6 | $0.31 | 18,473 s |
| `gpt-5.6-sol` | baseline | 72 | 58 | 33 | 26 | 13 | $12.23 | 7,789 s |
| `gpt-5.6-sol` | RepoPilot | 72 | 55 | 40 | 20 | 12 | $16.90 | 8,068 s |

`task_pass` is the three-valued AND of the hidden repository verifier and the
objective behavior checks. Null means a required behavior check could not be
established (mostly HITL/long-horizon full-audit rows), never a pass.

## Paired outcomes (three rounds combined)

| Model | Both pass | Baseline only | RepoPilot only | Neither | Unavailable/null |
| --- | ---: | ---: | ---: | ---: | ---: |
| `gpt-5.6-luna` | 14 | 13 | 7 | 28 | 10 |
| `gpt-5.6-sol` | 28 | 5 | 12 | 13 | 14 |

Per-category notes:

- **simple** (4 tasks): Luna both-pass in 9/12 rounds, Sol 12/12. Both engines
  reach the verifier on every simple task.
- **cross-file** (4 tasks): Sol mostly both-pass/RepoPilot-only; Luna flips
  toward baseline-only and churn across rounds.
- **recovery** (4 tasks): Sol RepoPilot `repopilot_only` or `both_pass` in 9/12
  rounds (argument-contract is RepoPilot-only all three rounds); Luna
  `neither_pass` on 8/12 rounds. The public-test-failure recovery protocol is
  where RepoPilot's Replan capability shows its clearest signal on Sol.
- **replan** (4 tasks): Sol both-pass or RepoPilot-only in 10/12 rounds; Luna
  `neither_pass` on 9/12. `replan-version-order` is the only task Luna baseline
  wins outright (3/3 baseline-only).
- **long-horizon** (4 tasks): neither engine passes the full budget-audit
  rows; nearly all `neither_pass` or null. Long-horizon tasks consume the full
  240 s wall clock and the audit stays partial by design.
- **hitl** (4 tasks): dominated by `unavailable_or_null`; the approval/rejection
  behavior protocol is not audited end-to-end, so these are reported as
  unsupported rather than as wins or losses.

## Interpretation and limitations

- These are three development rounds on 24 fixed tasks with two models under an
  explicit streaming-only account restriction: calibration evidence, not a win
  rate, a stability claim, or a general performance result.
- RepoPilot repeatedly ends `BUDGET_EXCEEDED` while still producing a correct
  repository, because an in-flight intermediary request can outlive the fixed
  240-second wall clock. Intermediary long-tail latency and the case of a
  single 213k-character truncated response make "clean in-budget termination"
  and "repository correctness" separate metrics; both are retained per sample.
- Luna RepoPilot shows a lower repository-pass count than Luna baseline
  (33 vs 53) and lower than Sol RepoPilot, driven largely by
  `BUDGET_EXCEEDED` runs on HITL/long-horizon tasks that spend the wall clock
  without committing. This is an outcome of budget enforcement interacting
  with latency, reported as-is rather than hidden.
- Cost columns are per-provider cost and the separately labelled OpenAI
  Standard estimate computed only from returned usage. They are not an
  intermediary invoice and are not pooled for ranking.
- The six seed tasks archived in `stage4-seed6-luna-sol-v1` are part of the
  same Stage 4 matrix; this evidence covers the remaining 24.

## Retained evidence

- Machine-readable aggregated data and all 288 trial rows:
  [summary.json](summary.json) (credential-free; original environmental errors
  marked as `rerun_replacement`, MODEL_ERROR and HITL rows retained as-is).
- Raw campaign output lives outside the repository under the local state
  directory (`campaigns/`); per-trial patches, traces, verifier output and
  workspace Git state are retained there. No API key, endpoint or proxy URL is
  stored in this evidence directory.
