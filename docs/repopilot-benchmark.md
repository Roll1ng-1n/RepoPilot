# Agent Benchmark

`repopilot benchmark` runs the bundled target-repository tasks in Docker and compares the pinned mini-SWE-agent
baseline with RepoPilot under one shared configuration.

```bash
repopilot benchmark \
  --model provider/model-name \
  --image python:3.12-slim
```

Both engines run by default. Repeat `--engine baseline` or `--engine repopilot` to select a subset. The command
also accepts one model temperature and one Run Budget (`--max-steps`, `--max-replans`,
`--max-consecutive-failures`, `--command-timeout-seconds`, and `--max-run-seconds`). The same model name,
temperature, Docker image, task statement, step limit, command timeout, and wall-time limit are passed to both
engines. Baseline concepts with no equivalent, including Replan and structured Recovery counts, are recorded as
`null` rather than inferred.

The bundled suite contains two fixed snapshots:

- `seed-single-file` asks the agent to repair whitespace handling in a small slugification function.
- `seed-cross-file` asks the agent to add one option consistently across a greeting library and CLI.

Each manifest records a snapshot revision and canonical SHA-256. The runner rejects changed snapshot contents,
copies each valid snapshot into separate engine workspaces, and initializes the same Git baseline. The hidden Task
Verification remains outside the Target Repository and runs only after the Agent Run has ended. Its exit code—not
the agent's self-reported status—determines task success.

Every invocation creates a new directory below the platform RepoPilot state directory under `benchmarks/`, or
below `--state-dir` when provided. It retains:

- `config.json`, `summary.json`, and a side-by-side `summary.md`;
- an independent workspace and `result.json` for each task/engine pair;
- the baseline's complete `trajectory.json` or RepoPilot's Run artifacts;
- hidden verification output, elapsed time, the final patch, and commits after the fixed initial revision;
- steps, tokens, cost, Tool Calls, errors, Retry, and Replan metrics when the engine exposes real values.

Unavailable provider usage or price data is stored as JSON `null`. RepoPilot does not estimate tokens, prices,
or performance, and the repository contains no prefilled benchmark results. Running the command can make paid
model calls and may pull the configured Docker image.
