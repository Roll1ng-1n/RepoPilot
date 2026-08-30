# RepoPilot V1 capability source matrix

This matrix distinguishes what RepoPilot inherits from the pinned mini-SWE-agent base, what it extends at a
composition seam, and what is new in the `repopilot` package. A capability is described as implemented only when a
CLI path, Runtime Test, Trace/artifact, or source path provides concrete evidence. The evidence below is repository
evidence; it is not a claim that every external model, Docker host, or Target Repository will succeed.

## Upstream reuse

| Capability | Classification | Evidence |
| --- | --- | --- |
| Baseline Agent and trajectory execution | Upstream reuse | Trigger: `repopilot benchmark --engine baseline`; test: `tests/repopilot/test_benchmark.py`; artifact: baseline `trajectory.json`; limit: it has no RepoPilot Replan/structured Recovery metrics, which remain `null`. |
| LiteLLM/provider model adapters | Upstream reuse | Trigger: `repopilot run --model ...` and both benchmark commands; test: `tests/repopilot/test_model_metrics.py`; Trace: `model_response` usage/cost; limit: native Tool Calling/provider availability and returned usage are external requirements. Provenance is in [UPSTREAM.md](../UPSTREAM.md). |
| Basic Docker lifecycle | Upstream reuse with RepoPilot adapter | Trigger: `repopilot run --environment docker --image ...`, `benchmark`, and `swebench-smoke`; tests: `tests/repopilot/test_environment.py`; artifact: environment/preflight errors in result and Trace; limit: the host daemon and image must already be usable, and Docker is not claimed as a complete security boundary. |
| Upstream step, cost, wall-time, retry, and trajectory primitives | Upstream reuse | Trigger: baseline benchmark budget flags; test: `tests/repopilot/test_benchmark.py`; artifact: baseline `trajectory.json` and normalized metrics; limit: unsupported structured metrics are `null`, and provider cost is not estimated. |

These inherited pieces are intentionally not presented as RepoPilot inventions. RepoPilot keeps the recognizable
`minisweagent` package and records the exact v2.4.6 source revision in [UPSTREAM.md](../UPSTREAM.md).

## RepoPilot extensions

| Capability | Classification | CLI / test / Trace / source evidence |
| --- | --- | --- |
| Replaceable Local and Docker Execution Environment protocol | RepoPilot extension | `repopilot run --environment local|docker`; protocol and adapters in `src/repopilot/environment.py`; contract tests in `tests/repopilot/test_environment.py`. |
| Native Tool Registry for repository operations | RepoPilot extension | `src/repopilot/tools.py` validates and dispatches `list_files`, `search_code`, `read_file`, `apply_patch`, `view_diff`, and `run_command`; the structured calls are exercised through `tests/repopilot/test_cli_run.py`. |
| Explicit versioned Plan and Replan | RepoPilot extension | Agent prompt and `update_plan`/`replan` tools in `src/repopilot/runtime.py` and `src/repopilot/tools.py`; `tests/repopilot/test_plan.py` and `test_cli_run.py`; Trace events `plan_created` and `plan_replanned`. |
| Bounded Recovery and Run Budget | RepoPilot extension | Budget flags on `repopilot run`; `src/repopilot/budget.py` and `src/repopilot/recovery.py`; `tests/repopilot/test_cli_run.py` asserts `RETRY_MODEL`, `DEBUG_OBSERVATION`, `REPLAN`, and `BUDGET_EXCEEDED` evidence. |
| Checkpoint and Resume state | RepoPilot extension | `repopilot resume RUN_ID`; persistence in `src/repopilot/artifacts.py` and repository identity checks in `src/repopilot/checkpoint.py`; `tests/repopilot/test_cli_run.py` covers STOPPED resume and checkpoint state. |
| Context strategies | RepoPilot extension | `repopilot run --context-strategy none|sliding_window|summary`; `src/repopilot/context.py`; `tests/repopilot/test_context_runtime.py`; Trace event `context_summary_created`. |
| Human Approval risk policy | RepoPilot extension | `repopilot approve`/`reject`; `src/repopilot/approval.py`; `tests/repopilot/test_approval_runtime.py`; Trace events `approval_requested`, `approval_granted`, and `approval_rejected`. |
| Local Git commit Tool | RepoPilot extension | `git_commit` in `src/repopilot/tools.py`; approval/commit assertions in `tests/repopilot/test_approval_runtime.py`; commit reason/hash are persisted in metadata, report, and `git_commit` Trace events. |
| Model usage normalization | RepoPilot extension | `src/repopilot/model.py` normalizes provider usage/cost; `tests/repopilot/test_model_metrics.py`; missing usage/cost remains JSON `null` rather than being estimated. |

## RepoPilot additions

| Capability | Classification | CLI / test / Trace / source evidence |
| --- | --- | --- |
| Task Verification as the success gate | RepoPilot addition | `verify_task` and terminal status handling in `src/repopilot/tools.py` and `src/repopilot/runtime.py`; `tests/repopilot/test_cli_run.py` asserts passed verification yields `SUCCEEDED`, while missing evidence yields `UNVERIFIED`; Trace event `task_verification`. |
| Complete per-run artifact bundle and task report | RepoPilot addition | `src/repopilot/runtime.py` writes `metadata.json`, `checkpoint.json`, `trace.jsonl`, `plan.json`, `patch.diff`, `verification.json`, and `task_report.md`; `tests/repopilot/test_cli_run.py` checks the terminal bundle. |
| Read-only persisted-run inspection | RepoPilot addition | `repopilot inspect RUN_ID [--json]`; `src/repopilot/inspection.py`; `tests/repopilot/test_cli_inspect.py` verifies normalized state, complete Trace, and no execution on inspection. |
| Fixed, verifier-isolated Agent Benchmark | RepoPilot addition | `repopilot benchmark` and repeated `--task`; `src/repopilot/benchmark.py`; `tests/repopilot/test_benchmark.py`, `tests/repopilot/test_benchmark_workflow_tasks.py`, and [benchmark details](repopilot-benchmark.md). |
| Explicit unavailable-environment result | RepoPilot addition | Benchmark result status `ENVIRONMENT_UNAVAILABLE` in `src/repopilot/benchmark.py`; `tests/repopilot/test_benchmark.py` covers no verifier execution when Docker setup fails. |
| Model-backed fixed-task smoke evidence | RepoPilot addition | The [redacted smoke summary](evidence/model-backed-smoke-v1/summary.md) and [normalized results](evidence/model-backed-smoke-v1/summary.json) record one `seed-single-file` task under shared model, temperature, Run Budget, and Docker settings: baseline `Submitted`/hidden verifier `true` (7 steps, 19,660 tokens, 7 Tool Calls, 20.475s) and RepoPilot `SUCCEEDED`/verifier `true` (7 steps, 28,212 tokens, 9 Tool Calls, 0 retries, 0 replans, 19.723s); `cost` is `null`. The model name and endpoint are redacted, the API-key scan is clean, and this is smoke evidence, not a statistical win rate. |
| SWE-bench Lite smoke evidence | RepoPilot addition | `src/repopilot/swebench_smoke.py` and `tests/repopilot/test_swebench_smoke.py`; the [raw result](evidence/swebench-lite-smoke-v1/sqlfluff__sqlfluff-1625/result.json) uses `swebench` 5.0.2 and records `READY` Docker/gold preflight (`resolved: true`), then 5 model calls before `BUDGET_EXCEEDED` at `max_steps=5`; no patch, final verifier not run, `success: null`, duration 27.4755s, `cost: null`. Model/endpoint are redacted, API-key scan is clean; this is negative smoke evidence, not a SWE-bench score. |

## Reading the evidence

CLI output, metadata, Checkpoints, and JSONL Trace are the public seams for a Run. Tests named above are Runtime
Tests, while the six benchmark task verifiers are separate host-side Task Verification. A passing Runtime Test proves
the RepoPilot control flow under that test's controlled inputs; it does not prove a model call, Docker image, or
external SWE-bench run is available. The current SWE-bench smoke passed its `READY` preflight but ended
`BUDGET_EXCEEDED` before producing a patch or running the final verifier (`success: null`); it is real negative smoke
evidence, not a SWE-bench score or a performance number.
