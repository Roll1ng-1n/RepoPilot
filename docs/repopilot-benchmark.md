# Stage 4 Agent Benchmark

Stage 4 evaluates repository outcomes **and** objective evidence of the requested
Agent behavior. It reuses the Docker runner, hidden host verifiers, model adapters,
Git artifacts and campaign from Stage 3; it does not change core Agent behavior.
The fixed suite has 30 tasks, five in each category. It is a development suite of
small synthetic repositories, not evidence of general software-engineering ability.

The [Stage 3 result](evidence/four-model-stage3-v1/summary.md) remains historical:
one round, six tasks, three RepoPilot false failures, and a Git-image confound.
Its repository pass counts must not be relabelled as Stage 4 capability scores.
No new paid model results are prefilled by this implementation.

## Run and repeat

Build the Git-enabled image; Stage 0 resolves its immutable image ID and checks
Python and Git before any model call. Both engines receive the same snapshot,
prompt, model parameters, image, and effective task budget.

```bash
docker build -t repopilot-benchmark:py312-git docker/benchmark
repopilot benchmark --model provider/model-name --repeats 3 \
  --image repopilot-benchmark:py312-git --task recovery-import-path
repopilot campaign --model gpt-5.6-luna --model gpt-5.6-sol --repeats 3 \
  --image repopilot-benchmark:py312-git
```

Future comparison runs use `gpt-5.6-luna` and `gpt-5.6-sol` only;
`gpt-5.6-terra` and `gpt-5.5` do not enter new campaigns. The four-model
Stage 1-3 runs and pricing table remain historical records.

Repeat `--task` or `--engine baseline --engine repopilot` to select a subset.
Omitting tasks selects all 30. CLI defaults to three repeats; use `--repeats 5`
for a final campaign when appropriate. `campaign --rounds` is an alias for
`--repeats`. Programmatic `BenchmarkConfig(repeats=...)` and
`CampaignConfig(repeats=...)` support the same repetitions; their default remains
one for backwards compatibility. Do not nest repeats inside campaign rounds.

Each model/task/engine/repeat has a fresh workspace, UUID run ID, result and raw
artifacts. Paired keys are model + campaign round + benchmark repeat + task;
missing/unevaluable counterparts are reported separately. Existing trial
artifacts are never deleted to rerun an attempt: choose a fresh output root.
Engine order is deterministic, baseline then RepoPilot, and is not randomized.
Sequential order and provider drift remain experimental limitations.

Proxy policy (`none`, `inherit`, `explicit`) is shared. Endpoint credentials and
proxy URLs are redacted from retained traces/configuration. Unavailable Docker
or missing Python/Git produces `ENVIRONMENT_UNAVAILABLE`, not a fabricated failure
of the model's repository change. The manifest budget overrides benchmark defaults
and is capped by its task timeout; both adapters receive that effective budget.
Baseline does not implement native Replan or consecutive-failure budgets, so equal
configuration must not be interpreted as equal enforcement of those concepts.

## Two verification dimensions

Every result retains legacy `success` as repository-only success and additionally
records:

- `repository_pass`: hidden verifier exit code zero, or `null` if unavailable.
- `behavior_pass`: conjunction of required objective checks; `null` when evidence
  cannot establish a required check. No requirements means `true` (not applicable).
- `task_pass`: three-valued AND of repository and behavior. Any definite failure
  makes it false; otherwise unknown evidence remains null.

A task whose required scenario was observable but never triggered fails behavior.
An adapter without the necessary observation channel is unsupported, not a pass.
Each check includes its reason. The summary shows pass/evaluated and unavailable
counts; these counts must accompany rates, especially for experimental categories.
Repository and behavior coverage counts are separately retained in JSON.

The hidden verifier and `solution.json` fixtures stay outside the target workspace.
Fixtures are used only for evaluator tests, never by engine executors. Verifiers
check held-out values, incomplete repairs and Git state as applicable; their
assertions are not injected into model prompts.

## Fixed categories

| Category | Tasks | Intended evidence |
| --- | ---: | --- |
| Simple | 5 | Single-file regression/control: slugification, chunking, clamping, interval overlap, boolean parsing. |
| Cross-file | 5 | Greeting CLI, CSV export, pagination, pricing and search across module interfaces. |
| Recovery | 5 | Public command must fail before editing and pass after correction, with the public test files unchanged. |
| Replan | 5 | Initial concrete strategy in PLAN.md, observed new evidence, changed protocol/algorithm strategy, final hidden correctness. |
| Long-horizon | 5 | Existing workflow seed and four six-module pipelines: expenses, inventory, access logs, release notes. |
| HITL / Safety | 5 | Local commit request; approved changes committed or rejected changes retained without committing. Experimental behavior audit. |

Each manifest declares `category`, `capabilities`, `behavior_requirements`, immutable
snapshot revision/hash, statement, verifier and budget. Existing seed IDs are kept.
The old long-chain seed is smaller than the new pipelines. Real step distributions
and category difficulty still need model-backed calibration; a many-file task does
not by itself prove a long execution horizon.

## Objective behavior protocol

`evaluation.py` reads runtime trace facts and benchmark-only environment observations.
It never asks another LLM to judge behavior and never treats assistant prose as
structured instrumentation. The environment observer is shared by both engines;
it observes commands and plan files without issuing extra commands or changing
model observations. Environment events use `observation_index` (command boundaries),
not an estimated Agent step number. Native trace steps retain their original meaning.

Recovery manifests declare, for example:

```json
{
  "behavior_requirements": ["recovery"],
  "behavior_spec": {
    "recovery_command": "python public_test.py",
    "recovery_files": ["public_test.py"]
  }
}
```

An exact public command failure opens a scenario. Further executions of that
command are recovery attempts; successful execution with original public test
file hashes resolves it. A different successful read/search is not recovery.
Triggers have distinct IDs, and failure types are retained. This is deliberately
scoped to declared scenarios; recovery from arbitrary native errors is not inferred.
Exact command matching does not parse compound shell commands or aliases. The task
explicitly requests the canonical command; use it as a standalone invocation.

Replan manifests declare `evidence_command`, `evidence_marker`, `plan_path`,
`before_strategy` and `after_strategy`. The task tells both engines to write an
initial plan, execute the evidence command, then revise the plan. The observer
requires the old strategy before evidence, and its replacement with the concrete
new strategy after evidence at a later command boundary. Examples include
codepoint offsets → UTF-8 byte offsets and lexicographic → numeric version order.
Version increments, completed-step status changes and `update_plan` calls alone
do not qualify. Final hidden verification independently establishes the resulting
implementation. This protocol measures an explicit strategy transition in the
shared task, not whether RepoPilot's private native `replan` API was called; native
plan events are retained separately. Keyword-based strategy contracts do not prove
the quality of every free-form plan step.

For additional task-specific behavior checks, add a host-only Python script and
set `"behavior_verifier": "verify_behavior.py"`. It receives the trial artifact
directory as its sole argument. Read `evaluation-events.json`,
`evaluation-context.json`, `patch.diff`, and `workspace/`; output JSON on stdout:

```json
{"checks": {"recovery": {"pass": true, "reason": "Linked failure resolved by the required repair"}}}
```

Return every required check, with boolean/null `pass` and an explanatory reason.
Nonzero exit, timeout, malformed JSON, or missing required checks makes behavior
unsupported and preserves the reason. Custom checks should use objective facts;
never accept a model's claimed success as proof. The built-in requirement names
are `recovery`, `replan`, `approval`, `budget`, and `termination`; extend the
registry when adding a new kind of required behavior.

## Metrics and denominators

`summary.json.evaluation_summary` groups by model/engine and independently by task,
category and capability. A task may appear under several capabilities; those rows
must not be summed into an overall trial count. `summary.md` leads with task pass,
category/capability pass, successful termination, recovery, LLM calls/solved,
tokens/solved, tool failures/solved and churn availability, followed by paired
counts and legacy raw results. Latency remains secondary.

- Successful termination = correct-success cases / cases with known final status
  and repository verdict. `Submitted`, `SUCCEEDED`, `SUCCESS` mean agent success.
  False success and false failure use the same denominator. JSON also includes
  the four counts, completion precision and recall. Unknown status is excluded.
- Recovery rate = resolved declared scenarios / triggered declared scenarios.
  Trigger/attempt/resolved counts and post-recovery repository success are retained.
- Replan trigger rate = linked observed revisions / evidence scenarios; success
  rate = verified substantive revisions / evidence scenarios. Post-replan
  repository success is separate. Unnecessary replans are unsupported.
- Cost per solved = total measured consumption across **all** attempted tasks in
  the group / number of `task_pass=true` trials. Thus failures consume cost.
  JSON also reports consumption distributions restricted to solved trials, avoiding
  confusion with “average cost of successful attempts only.” Zero solved gives null.
- Calls, steps, tool calls, retries, replans, redundant native calls,
  input/output/total tokens and wall duration retain total, n, mean, median,
  sample standard deviation, min and max. Missing observations reduce n; a
  partially missing metric makes the total and cost-per-solved null. Baseline
  rows report null retries/replans because that engine records no native
  retry/replan accounting.
- Tool failures include failed tool envelopes and nonzero command exit codes nested
  inside otherwise successful envelopes. Baseline command failures use recorded
  trajectory return codes. Tool recovery is scoped to declared public commands.
- Redundancy counts only adjacent identical native read/search/list requests with
  equal arguments and equal successful stdout. No shell parsing or semantic claim
  is made; baseline shell redundancy stays unsupported.

Pair tables contain both pass, left only, right only, neither and unavailable for
each same-model engine pair, overall and per category. For baseline/RepoPilot these
are the requested baseline-only and RepoPilot-only counts. Arbitrary engine pairs
use their registered IDs. Do not pool token costs across models for a tokenizer-
independent ranking; cross-model comparisons should emphasize pass rates and calls.
No confidence or stability claim follows from a single round.

## Reproduce evidence from raw state

`docs/evidence/*/summary.json` is a curated redaction. Its rows keep the headline
verdicts but not every per-row `metrics`/`evaluation` object, so it cannot rebuild
the full `evaluation_summary`. The raw per-campaign `summary.json` files written by
`repopilot campaign` under `~/.local/state/repopilot/campaigns/<run-id>/` can.
`src/repopilot/recompute.py` merges several raw summaries with deterministic
overlay semantics and reruns the same `evaluation.aggregate`/`markdown` used by
the runner:

```bash
python -m repopilot.recompute \
  --title "Stage 4 - 24 tasks (luna vs sol)" \
  --out-json docs/evidence/stage4-24tasks-luna-sol-v1/recomputed.json \
  --out-markdown docs/evidence/stage4-24tasks-luna-sol-v1/recomputed.md \
  ~/.local/state/repopilot/campaigns/<main-run>/summary.json \
  ~/.local/state/repopilot/campaigns/<rerun-root-a>/summary.json
```

Files are consumed in argument order. A row is identified by
`(model, round, task_id, engine)`; a later file replaces an earlier row with the
same key, so an environmental-error rerun root overwrites the failed row without
double counting. A row without a real status never replaces one that has a status.
The 360-sample Stage 4 evidence combines two raw campaign groups:

- 24 tasks (288 samples): main 24-task run plus the two rerun roots that replaced
  three baseline environmental-error trials.
- Seed 6 tasks (72 samples): `seed-cross-file`, `recovery-public-failure`,
  `replan-new-evidence`, `workflow-long-chain`, `workflow-human-approval-git`
  plus `seed-single-file` from its separate clean run.

The committed `recomputed.json`/`recomputed.md` files under `docs/evidence/`
are the output of the commands above for those exact run IDs. `recomputed.json`
holds the full recomputed `evaluation_summary` plus a compact merged-row
inventory (`models`/`engines`/`rounds`/`statuses`) so the file stays small;
full per-row objects remain in raw state and can be embedded with
`--include-rows` for debugging. The merge overlay was verified to reproduce the
curated `summary.json` row keys and statuses one-to-one (zero differences).
Curated `summary.md` remains the primary readable narrative; `recomputed.md` is
the machine-recomputable table.

## Supported and deferred instrumentation

| Measurement | Current support / missing evidence |
| --- | --- |
| Repository, declared Recovery and Replan | Implemented; exact public command/strategy contracts above. |
| Final termination confusion matrix | Implemented. Timely stopping is not implied by correct final status. |
| LLM calls, tokens, tool failures, repeated trials, paired/category/capability summaries | Implemented where source records exist; null otherwise. |
| HITL complete behavior | **Unsupported / experimental**. Native approval requests and decisions are retained. The harness resumes native requests using manifest `approval_policy=approve/reject`, within the remaining observed wall time. Baseline has no equivalent structured approval protocol. Neither trace supplies an exhaustive audit of shell effects/bypasses, so auto-approval or a commit alone never gives a safety pass. A future adapter must provide a complete `approval_audit` including requests, respected decisions and zero bypasses, or a task-specific host checker. |
| Full execution-budget behavior | **Unsupported** without a complete `budget_audit`. Configured limits and used steps/replans are retained. Baseline lacks failure/replan enforcement; in-flight model calls may exceed wall time and runtime resume does not preserve a monotonic origin. Full deadline/cancellation and ordered failure accounting are required before passing this check. Long-horizon tasks require budget and therefore may have unknown task verdicts even when repositories pass. |
| First solved step / post-solution steps, calls, tokens | **Unsupported**. Need immutable per-step repository states (including untracked/deleted files and Git history where relevant), isolated replay and hidden verification at every boundary, plus step-linked usage. Final patch and self-reported verification are insufficient. |
| API duration | RepoPilot sums recorded model-response durations only when all available response durations exist. Baseline unavailable. |
| Full tool execution duration / orchestration overhead | **Unsupported**. Need complete non-overlapping monotonic spans for every command, tool, model wait and lifecycle work. Existing partial durations do not justify subtracting a precise overhead. |
| Arbitrary error recovery / unnecessary replans | **Deferred**. Need causal error-resolution IDs and task-specific evidence of necessity; later success or raw Replan count is insufficient. |

Unsupported behavior does not imply either engine lacks that capability. It means
the current evaluation cannot substantiate the claim. In particular, this release
provides the pipeline and task fixtures for safety/budget experiments, not completed
safety or full budget validation.

## Add tasks and ablations

1. Add `benchmark_tasks/<id>/snapshot/`, manifest, a host-only verifier and a
   host-only `solution.json` mapping relative paths to repaired contents.
2. Declare category/capabilities, objective required behavior, public scenario
   commands, budget and timeouts. Use different behavior contracts only where the
   task actually requires them. Calculate `canonical_snapshot_sha256(snapshot)`
   after all snapshot edits; never include hidden checks in that snapshot.
3. Run `pytest tests/repopilot/test_stage4_tasks.py`: initial snapshots must fail,
   complete solutions must pass, and each required changed file must matter.
   Add public-test-passing wrong implementations as negative verifier cases.
4. Run a small selected model/task campaign before full repetitions. Retain raw
   artifacts, unsupported counts and environment failures. Keep task/version,
   engine configuration and model parameters fixed across paired trials.
5. Register a new engine executor using the existing Python seam, for example
   `BenchmarkRunner(config, executors={"repopilot-no-planner": executor})` with
   `config.engines=("baseline", "repopilot-no-planner")`. Use `run_campaign`'s
   same `executors` seam for multi-model experiments. Unknown adapters fail before
   execution. CLI engine selection still exposes the two built-ins.

An executor receives `EngineRequest` (workspace, task, effective budget and model
configuration) and returns `EngineRun` with source metrics/artifacts. Canonical
`evaluation_events` must be generated by the harness from observations, not copied
from model-generated JSON. Variant IDs are safe directory identifiers, and the
aggregator handles every engine pair. No ablation behavior is implemented or
silently substituted by this framework; disabling a mechanism belongs in its
separate executor/configuration experiment.
