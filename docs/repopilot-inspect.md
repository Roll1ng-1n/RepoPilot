# Inspecting an Agent Run

Use `inspect` to review a persisted Agent Run without resuming it, creating a model or Execution Environment, or
executing a command in the Target Repository.

```bash
repopilot inspect <run-id>
repopilot inspect <run-id> --state-dir /path/to/agent-runs
repopilot inspect <run-id> --state-dir /path/to/agent-runs --json
```

The default state directory is the platform-specific `platformdirs` state directory for RepoPilot, under `runs`.
`run` prints both the Run ID and artifacts directory; use the Run ID with this command and the artifacts directory to
identify the corresponding state directory when needed. `metadata.json` is preferred for completed Runs. If it is
not present, inspect uses the latest `checkpoint.json`, which also makes a RUNNING or interrupted Run inspectable.

Human-readable output includes the Run status, task, Target Repository, model, current Plan and Plan History, Budget,
Recovery, Context, Human Approval state, Task Verification results, Git commits, every Trace event, each artifact path,
and the task report. `--json` emits one machine-readable document with the same normalized state and the complete Trace.

Each Agent Run uses a directory containing these seven artifact types:

1. `metadata.json` — terminal Run metadata.
2. `checkpoint.json` — resumable Run state.
3. `trace.jsonl` — append-only Trace events.
4. `plan.json` — the current Plan and complete Plan History.
5. `patch.diff` — current or committed patch captured when the Run pauses or ends.
6. `verification.json` — Task Verification evidence collected so far.
7. `task_report.md` — the human-readable completion or status report.

The complete artifact set is generated when the Runtime pauses or records a terminal status. A Run that is actively
RUNNING may temporarily have only its Checkpoint and Trace; inspect uses the Checkpoint until metadata is available.

## Known limitations

- Trace inspection shows the events RepoPilot persisted, but Trace does not currently provide a cross-provider
  normalized token or cost view.
- Artifact redaction only covers credential values known to the CLI from the API key and environment variables whose
  names contain `KEY`, `TOKEN`, `SECRET`, or `PASSWORD`; it is not a general secret scanner.
- Inspect is read-only and does not recover a Run, replay commands, validate the current Target Repository, or render
  the full Checkpoint message history.
