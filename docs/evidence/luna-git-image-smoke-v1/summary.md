# Git-enabled benchmark image smoke

Issue: [#18](https://github.com/Roll1ng-1n/RepoPilot/issues/18). This evidence checks the
environment fix that must precede Stage 4; the historical Stage 3 results remain unchanged.

## Frozen environment

- Platform: Linux amd64.
- Build: `docker build -t repopilot-benchmark:py312-git docker/benchmark`.
- Python base: `python:3.12-slim@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea`.
- Debian and Debian security snapshot: `20260901T000000Z`.
- Resulting image: `repopilot-benchmark@sha256:0e67c51e0bf6da98d57610cbcedf707dcef207aef304b5c2b5fc972e5ba11ecc`.
- Container checks: `Python 3.12.14`, `git version 2.47.3`, both exit code 0.
- Container proxy mode: `none`.

The digest identifies the actual local build used for this run. Rebuilding freezes package
inputs but may produce a different digest because build metadata/timestamps can vary.
Use the recorded digest for paired runs on this Docker daemon; this image has not been
published to a registry.

## Paired run

Only `gpt-5.6-luna`, `workflow-human-approval-git`, baseline and RepoPilot, one round.
The shared task budget is 15 steps, one Replan, two consecutive failures, 30-second
command timeout and a 180-second Agent Run budget. A pending model request may return
after that wall-clock budget, as already observed in Stage 3.

| Engine | Agent status | Verifier | Steps | Commits | Tokens | Agent duration | Official Standard estimate |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| baseline | `TimeExceeded` | failed (exit 1) | 4 | 0 | 12,069 | 413.15 s | $0.00327518 |
| RepoPilot | `BUDGET_EXCEEDED` | failed (exit 1) | 1 | 0 | 1,068 | 290.25 s | $0.00025160 |

Both results record the same image digest above and successful Python/Git preflight checks.
The baseline produced a patch but no commit; RepoPilot exhausted its wall-clock budget
after its first model response. Neither passed the hidden verifier. This confirms the
container dependency fix, but does **not** establish successful end-to-end Git task completion
or clear the overall Stage 4 gate. No retry or expanded campaign was run.

The combined official Standard estimate is **$0.00352678**, based on returned usage; it is
not an intermediary invoice. A subsequent test is expected to use a model's official API
to avoid confounding the comparison with this intermediary's response latency.

Retained evidence (workspace copies and their `.git` directories are excluded):

- [Campaign configuration and results](artifacts/summary.json).
- [Stage 0 checks](artifacts/gpt-5.6-luna/round-001/preflight.json).
- [Baseline result and verifier](artifacts/gpt-5.6-luna/round-001/workflow-human-approval-git/baseline/result.json),
  [trajectory](artifacts/gpt-5.6-luna/round-001/workflow-human-approval-git/baseline/trajectory.json),
  [patch](artifacts/gpt-5.6-luna/round-001/workflow-human-approval-git/baseline/patch.diff).
- [RepoPilot result and verifier](artifacts/gpt-5.6-luna/round-001/workflow-human-approval-git/repopilot/result.json),
  [run state](artifacts/gpt-5.6-luna/round-001/workflow-human-approval-git/repopilot/run-state/2a0266238abb4d9088218cbf9a630496/).

Paths inside raw artifacts retain their original local run locations. API credentials,
endpoint and proxy URL values are redacted; only the selected proxy mode is public.

The original slim image was also exercised through the new runner with an unused model
name: both engines returned `ENVIRONMENT_UNAVAILABLE`, `success: null`, with no Agent
Run. Its [preflight evidence](old-image-preflight.json) records the missing Git executable.

## Runtime validation

- Focused benchmark, CLI, campaign and workflow tests: 27 passed.
- Ruff across `src/repopilot` and `tests/repopilot`: passed.
- Full pytest invocation: 252 tests passed before a prolonged stall; interrupted rather
  than reported as a full-suite pass. No failure had been printed.
- A standalone type checker is not installed in the current virtual environment.
