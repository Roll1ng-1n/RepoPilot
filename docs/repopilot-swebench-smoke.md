# SWE-bench Lite smoke

RepoPilot's SWE-bench smoke is a bounded external check against one pinned
public SWE-bench Lite development instance. It supplements the local
micro-benchmark; it is not a claim about SWE-bench Lite, SWE-bench Verified, or
model performance in general.

## Fixed inputs and limits

The smoke keeps these inputs fixed so that a later result can be reproduced:

| Setting | Value |
| --- | --- |
| Dataset | `SWE-bench/SWE-bench_Lite` |
| Dataset revision | `b0dde1093fe417d83b7184254edf8199c1f0dff5` |
| Split | `dev` |
| Instance | `sqlfluff__sqlfluff-1625` |
| Docker image | `docker.io/swebench/sweb.eval.x86_64.sqlfluff_1776_sqlfluff-1625:latest` |
| Workers | `1` |
| Temperature | `0` |
| Maximum Agent Steps | `50` |
| Maximum Replans | `2` |
| Maximum consecutive failures | `3` |
| Command timeout | `300` seconds |
| Agent Run wall-time limit | `1800` seconds |

The smoke has one instance and one worker by design. It is a repeatable
integration seam, not a statistically powered benchmark. The model name and
provider credentials are supplied by the caller and are not written into this
document.

The complete path also requires the official `swebench` Python package in the
RepoPilot environment. If it is absent, verifier preflight records
`VERIFIER_UNAVAILABLE` before any model is constructed.

## Execution order

Use the smoke entry point with a model name for a complete model-backed run:

```bash
repopilot swebench-smoke \
  --model provider/model-name
```

Before creating a model or spending model credits, the smoke performs the
environment preflight:

1. `docker image inspect` checks that the pinned image is already available
   locally.
2. A Docker start check uses the image without an implicit pull and confirms
   the SWE-bench `/testbed` layout is usable.
3. The official SWE-bench harness is run as a verifier preflight.

If any Docker or verifier preflight check is unavailable, the smoke records
`ENVIRONMENT_UNAVAILABLE` (or `VERIFIER_UNAVAILABLE` for the verifier check),
does not construct a model, and does not make a model call. This preserves the
difference between an unavailable execution environment and a failed code
change. A missing local image is not silently pulled by the smoke.

The preflight can therefore be run without `--model`. If preflight succeeds
without a model, the smoke records `MODEL_UNAVAILABLE` with zero model calls;
provide `--model provider/model-name` when the environment is ready to run the
agent.

After a successful preflight, RepoPilot runs the pinned instance in the
Docker-backed environment and writes the patch and execution trace. The
official `swebench.harness.run_evaluation` invocation is a separate verifier;
the upstream mini-SWE-agent runner produces the agent trajectory but does not
itself establish SWE-bench success.

## Results and accounting

The intended evidence directory is:

```text
docs/evidence/swebench-lite-smoke-v1/
```

Each run retains its configuration, preflight checks, RepoPilot trace and
artifacts, patch, verifier output, and a machine-readable result. A result
with an unavailable Docker daemon/image, unavailable verifier, model failure,
budget termination, or failed verification remains in the evidence directory
with that status; no success value is inferred from an agent's self-report.

Token and cost fields are recorded only when the provider returns them. The
default `$3` cost guard stops another model call once observed cost reaches the
limit; a provider that omits cost data cannot be hard-limited by that guard.
Missing usage or cost is represented as JSON `null`, rather than estimated.

The [published result](evidence/swebench-lite-smoke-v1/sqlfluff__sqlfluff-1625/result.json)
uses the locally preloaded pinned image and `swebench` 5.0.2. Docker start,
`/testbed`, and the official gold-patch verifier preflight all passed
(`status: READY`, `gold resolved: true`). The authorized low-cost model was
called 5 times over 27.4755 seconds with `cost: null`; with `max_steps=5`, the
Agent ended `BUDGET_EXCEEDED` with no patch, the final verifier did not run,
and `success` is `null`. The model name and endpoint are redacted; the API-key
scan is clean. This is real negative smoke evidence, not a SWE-bench score.
The smoke covers only this one pinned instance;
full/complete Lite, Verified, SWE-bench-wide, SWT-Bench, and ProgramBench
evaluations remain out of scope for RepoPilot V1.
