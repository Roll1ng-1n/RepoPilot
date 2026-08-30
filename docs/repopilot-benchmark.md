# Agent Benchmark

`repopilot benchmark` runs the six bundled target-repository tasks in Docker and compares the pinned
mini-SWE-agent baseline with RepoPilot under one shared configuration. Each task is a small, fixed workflow that
is cheap to repeat while exercising a different Agent engineering behavior.

```bash
repopilot benchmark \
  --model provider/model-name \
  --image python:3.12-slim
```

Both engines run by default. Repeat `--engine baseline` or `--engine repopilot` to select a subset. Repeat `--task`
to select one or more fixed tasks for an independent run, for example:

```bash
repopilot benchmark \
  --model provider/model-name \
  --image python:3.12-slim \
  --task seed-cross-file \
  --task workflow-long-chain \
  --task workflow-human-approval-git
```

The selected task IDs are kept in the requested order. Omitting `--task` runs all six tasks. The command also
accepts one model temperature and one Run Budget (`--max-steps`, `--max-replans`, `--max-consecutive-failures`,
`--command-timeout-seconds`, and `--max-run-seconds`). The same model name, temperature, Docker image, task
statement, step limit, command timeout, and wall-time limit are passed to both engines. Baseline concepts with no
equivalent, including Replan and structured Recovery counts, are recorded as `null` rather than inferred.

## Fixed task suite

Every manifest records a fixed snapshot revision and canonical SHA-256, a task statement, a host-only hidden
verifier, a success condition, and timeouts. All six bundled tasks currently use a 180-second Agent Run timeout,
a 20-second verifier timeout, and the same 15-step/1-Replan/2-consecutive-failure Run Budget.

| Task | Focus | Observable behavior |
| --- | --- | --- |
| `seed-single-file` | Simple single-file bug | Repair whitespace normalization without changing punctuation. |
| `seed-cross-file` | Cross-file modification | Thread `--excited` through a greeting library and CLI while preserving the default. |
| `recovery-public-failure` | Verification failure and Recovery | Use public-test evidence to preserve spelling while applying case-insensitive deduplication. |
| `replan-new-evidence` | Replan from repository evidence | Inspect the docs/tests and implement newline-delimited JSON rather than an array. |
| `workflow-long-chain` | Long-chain exploration | Trace CLI → command → workflow → formatting across four small modules before fixing compact output. |
| `workflow-human-approval-git` | Human Approval and Git | Change the completed-status behavior and create a local commit after the benchmark's initial revision. |

The coverage matrix is intentionally task-level rather than a claim of broad software-engineering coverage:

| Agent behavior | Task evidence |
| --- | --- |
| Basic edit and Task Verification | `seed-single-file`, `seed-cross-file` |
| Cross-file data/control-flow tracing | `seed-cross-file`, `workflow-long-chain` |
| Failed verification followed by correction | `recovery-public-failure` |
| New repository evidence changing the plan | `replan-new-evidence` |
| Human Approval-compatible Git write and commit accounting | `workflow-human-approval-git` |

The hidden verifiers remain outside each Target Repository. They observe only the resulting external behavior (and,
for the Git task, the resulting local Git history); they do not expose their assertions to the Agent. The runner
rejects changed snapshot contents, copies each valid snapshot into separate engine workspaces, and initializes the
same fixed Git baseline before each engine run. The verifier runs on the host only after the Agent Run has ended,
and its exit code—not the agent's self-reported status—determines task success.

For `workflow-human-approval-git`, the Docker benchmark uses the explicitly disposable benchmark context and thus
automatically approves the RepoPilot Git Tool Call. The baseline can perform the equivalent local `git add`/`git
commit` through its shell. The result records commits after the initial revision; push, rebase, reset, and Pull
Request operations remain unsupported.

## Results and unavailable environments

Every invocation creates a new directory below the platform RepoPilot state directory under `benchmarks/`, or below
`--state-dir` when provided. It retains:

- `config.json`, `summary.json`, and a side-by-side `summary.md`;
- an independent workspace and `result.json` for each task/engine pair;
- the baseline's complete `trajectory.json` or RepoPilot's Run artifacts;
- hidden verification output, elapsed time, the final patch, and commits after the fixed initial revision;
- steps, tokens, cost, Tool Calls, errors, Retry, and Replan metrics when the engine exposes real values.

If Docker cannot be started or the configured image is unavailable, the affected run is recorded as
`ENVIRONMENT_UNAVAILABLE`. This is an execution-environment result, not evidence that the task's code change failed;
the benchmark retains the result and does not fabricate a verifier success. If an engine or provider does not
return a metric, the corresponding token, cost, or duration field is JSON `null`. The runner never estimates missing
usage, price, or timing data.

The default run has six fixed tasks and two engine attempts per task (12 task/engine samples). This is a small,
development-time regression suite for comparing the two local execution paths and catching changes in Planning,
Recovery, Replan, Human Approval, Git, and verification behavior. It is not a statistically powered benchmark and
does not support generalization or performance claims about models, repositories, or production workloads. Results
are raw evidence, including failures and unavailable environments. The checked-in [historical 12-sample summary](evidence/micro-benchmark-v1/summary.md)
records all 12 attempts as `ENVIRONMENT_UNAVAILABLE`, with zero model calls
and `success: null`; for that run, a model success rate is unavailable (0/0, not 0%).

The separate [model-backed smoke evidence](evidence/model-backed-smoke-v1/summary.md) records a real comparison on
the single `seed-single-file` task under the same redacted low-cost authorized model, temperature, Run Budget, and
Docker image. Baseline: `Submitted`, hidden verifier `true`, 7 steps, 19,660 total tokens, 7 Tool Calls, 20.475
seconds, `cost: null`. RepoPilot: `SUCCEEDED`, verifier `true`, 7 steps, 28,212 total tokens, 9 Tool Calls, 0
retries, 0 replans, 19.723 seconds, `cost: null`. The model name and endpoint are redacted; the API-key scan is
clean. This is one task with two engine attempts and is smoke evidence only, not a statistically meaningful win rate
or general performance claim. Running the command can make paid model calls and may pull the configured Docker image.
