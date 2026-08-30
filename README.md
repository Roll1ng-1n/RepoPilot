# RepoPilot V1 — 可评测、可恢复的软件工程 Agent

RepoPilot is a CLI-first software-engineering Agent for making bounded, explainable, and verifiable changes in a
Target Repository. A run forms a Plan, uses structured Tool Calls to inspect and modify code, runs Task Verification,
and leaves a Checkpoint, Trace, Patch, and human-readable report. The project is designed as a small, inspectable V1
for engineering workflows and learning—not as a claim of autonomous production safety or model performance.

RepoPilot is developed from the pinned mini-SWE-agent v2.4.6 source snapshot. The retained `minisweagent` package,
upstream license, and source attribution are described in [UPSTREAM.md](UPSTREAM.md). The [capability source
matrix](docs/repopilot-capabilities.md) separates upstream reuse, RepoPilot extensions, and RepoPilot additions.

## Install and quick demo

From a checkout, install the CLI and development dependencies in an isolated environment:

```bash
uv venv
source .venv/bin/activate
uv pip install -e ".[dev]"
```

`repopilot run` requires a model that supports OpenAI-compatible native Tool Calling and the provider's credentials.
The following is a minimal Local Environment invocation; Local runs execute commands directly in the Target
Repository:

```bash
export REPOPILOT_MODEL=provider/model-name
repopilot run /path/to/target-repository \
  --task "Fix the failing parser tests and verify the change." \
  --environment local
```

The CLI prints an Agent Run ID, current Plan, terminal status, and artifact directory. A successful run is not
assumed by this example: it depends on the configured model, repository, and verification evidence.

## CLI workflow

The same CLI exposes the main Agent Run lifecycle:

```bash
# Inspect a persisted run without executing it (use --json for one machine-readable document).
repopilot inspect RUN_ID --state-dir /path/to/state --json

# Resume a STOPPED run after recreating its Execution Environment.
repopilot resume RUN_ID --state-dir /path/to/state --model provider/model-name

# Resolve a pending Human Approval, then let the run continue from its Checkpoint.
repopilot approve RUN_ID --state-dir /path/to/state
repopilot reject RUN_ID --state-dir /path/to/state
```

`run` defaults to the Local Environment and prints an explicit warning because it can modify the Target Repository
directly. Pass `--environment docker --image python:3.12-slim` to use the Docker backend instead. Docker bind-mounts
the Target Repository at `/workspace`; it is an execution backend, not a complete security boundary. Docker may be
unavailable on a particular machine, in which case the benchmark records `ENVIRONMENT_UNAVAILABLE` rather than
silently falling back to Local execution.

## Architecture at a glance

The composition layer in `repopilot.cli` creates a model, Execution Environment, Tool Registry, Plan, Context
Strategy, Run Budget, and artifact store. `AgentRuntime` drives the bounded Agent Run. The Tool Registry validates
native Tool Calls and dispatches repository, command, verification, Git, and Agent Control operations. Local and
Docker backends implement the same Execution Environment protocol. Checkpoints make STOPPED and
`WAITING_FOR_APPROVAL` runs resumable; JSONL Trace events retain the complete audit history even when the prompt
context is compressed.

For a compact evidence map, see [Capability source matrix](docs/repopilot-capabilities.md). It links each stated
capability to the relevant CLI path, Runtime Test, Trace/artifact, or implementation source. The
[design validation record](docs/repopilot-design-validation-record.md) preserves selected failures, root causes,
fixes, verification, and associated commits.

## Fixed Agent Benchmark

```bash
repopilot benchmark \
  --model provider/model-name \
  --image python:3.12-slim \
  --task seed-cross-file \
  --task workflow-long-chain \
  --engine repopilot
```

Repeat `--task` to run selected fixed tasks; omit it to run the six-task suite. Repeat `--engine` to choose the
baseline, RepoPilot, or both. Each task has a fixed snapshot revision/hash, task statement, host-only hidden
verifier, success condition, timeout, and Run Budget. The runner creates independent Git workspaces and preserves
raw results, patches, commits, and verification output. See [benchmark details](docs/repopilot-benchmark.md) for the
task list and behavior coverage.

The checked-in [micro-benchmark summary](docs/evidence/micro-benchmark-v1/summary.md) contains 12 real
task/engine attempts. All are `ENVIRONMENT_UNAVAILABLE` because the configured Docker image was unavailable; no
model-backed task completed, so no success rate is reported.

The current SWE-bench Lite smoke record is deliberately not presented as a model result:

`ENVIRONMENT_UNAVAILABLE` — the pinned image preflight ran, but the Agent Run did not; no model was called. See the
[raw result](docs/evidence/swebench-lite-smoke-v1/sqlfluff__sqlfluff-1625/result.json).

A model-backed SWE-bench smoke additionally requires the official `swebench` Python package and the pinned image to
be available locally. Missing verifier or image prerequisites are recorded before a model is constructed.

```bash
uv pip install swebench
```

Missing provider usage, cost, or timing data is recorded as JSON `null`; RepoPilot does not estimate it. The six-task
benchmark is development-time regression evidence with a small fixed sample, not a statistically powered comparison
or a generalization claim.

## Known limitations and Out of Scope

- Local execution directly affects the Target Repository and should be treated as a developer-controlled environment.
- Docker isolation depends on the host and configured image; Docker is not presented as a complete security boundary.
- Model/provider availability, credentials, native Tool Calling support, and returned usage data are external
  dependencies. A failed or unavailable environment is evidence about execution availability, not task correctness.
- The benchmark has six tiny fixed tasks and does not establish success rates, cost rankings, or general performance.
- V1 formally verifies Python Target Repositories; other languages are not claimed as supported by this evidence.
- Human Approval is a lightweight best-effort risk policy. Git support is local commit only; push, pull, rebase,
  reset, and Pull Request creation are unsupported.
- RAG Memory, multi-agent orchestration, Web UI, remote execution backends, and full SWE-bench runs are out of scope.
- The SWE-bench Lite smoke is currently `ENVIRONMENT_UNAVAILABLE` and has no model-call result to report.

---

## Upstream mini-SWE-agent base

The material below is the retained upstream project overview for attribution. Its Docker, model, and SWE-bench
statements describe mini-SWE-agent upstream, not RepoPilot V1 runs or results.

<div align="center">
<a href="https://mini-swe-agent.com/latest/"><img src="https://github.com/SWE-agent/mini-swe-agent/raw/main/docs/assets/mini-swe-agent-banner.svg" alt="mini-swe-agent banner" style="height: 7em"/></a>
</div>

### The minimal AI software engineering agent

📣 [mini-swe-agent now powers Ramp SWE-Bench](https://labs.ramp.com/swebench)<br/>
📣 [mini-swe-agent beats Claude Code and Codex on DeepSWE](https://deepswe.datacurve.ai/blog#evaluation-harness)<br/>
📣 [Run mini-swe-agent on our new & extremely challenging benchmark, ProgramBench](https://mini-swe-agent.com/latest/usage/programbench/)<br/>
📣 [New tutorial on building minimal AI agents](https://minimal-agent.com/)

[![Docs](https://img.shields.io/badge/Docs-green?style=for-the-badge&logo=materialformkdocs&logoColor=white)](https://mini-swe-agent.com/latest/)
[![Slack](https://img.shields.io/badge/Slack-4A154B?style=for-the-badge&logo=slack&logoColor=white)](https://join.slack.com/t/swe-bench/shared_invite/zt-36pj9bu5s-o3_yXPZbaH2wVnxnss1EkQ)
[![PyPI - Version](https://img.shields.io/pypi/v/mini-swe-agent?style=for-the-badge&logo=python&logoColor=white&labelColor=black&color=deeppink)](https://pypi.org/project/mini-swe-agent/)

> [!WARNING]
> This is **mini-swe-agent v2**. Read the [migration guide](https://mini-swe-agent.com/latest/advanced/v2_migration/). For the previous version, check out the [v1 branch](https://github.com/SWE-agent/mini-swe-agent/tree/v1).

In 2024, we built [SWE-bench](https://github.com/swe-bench/SWE-bench) & [SWE-agent](https://github.com/swe-agent/swe-agent) and helped kickstart the coding agent revolution.

We now ask: **What if our agent was 100x simpler, and still worked nearly as well?**

`mini` is

- **Widely adopted**: Used by Meta, NVIDIA, Essential AI, IBM, Nebius, Anyscale, Princeton University, Stanford University, and many more.
- **Minimal**: Just some 100 lines of python for the [agent class](https://github.com/SWE-agent/mini-swe-agent/blob/main/src/minisweagent/agents/default.py) (and a bit more for the [environment](https://github.com/SWE-agent/mini-swe-agent/blob/main/src/minisweagent/environments/local.py),
[model](https://github.com/SWE-agent/mini-swe-agent/blob/main/src/minisweagent/models/litellm_model.py), and [run script](https://github.com/SWE-agent/mini-swe-agent/blob/main/src/minisweagent/run/hello_world.py)) — no fancy dependencies!
- **Performant:** Scores >74% on the [SWE-bench verified benchmark](https://www.swebench.com/); starts much faster than Claude Code
- **Deployable:** Supports **local environments**, **docker/podman**, **singularity/apptainer**, **bublewrap**, **contree**, and more
- **Compatible:** Supports all models via **litellm**, **openrouter**, **portkey**, and more. Support for `/completion` and `/response` endpoints, interleaved thinking etc.
- Built by the Princeton & Stanford team behind [SWE-bench](https://swebench.com), [SWE-agent](https://swe-agent.com), and more
- **Tested:** [![Codecov](https://img.shields.io/codecov/c/github/swe-agent/mini-swe-agent?style=flat-square)](https://codecov.io/gh/SWE-agent/mini-swe-agent)

<details>

<summary>More motivation (for research)</summary>

[SWE-agent](https://swe-agent.com/latest/) jump-started the development of AI agents in 2024. Back then, we placed a lot of emphasis on tools and special interfaces for the agent.
However, one year later, as LMs have become more capable, a lot of this is not needed at all to build a useful agent!
In fact, the `mini` agent

- **Does not have any tools other than bash** — it doesn't even need to use the tool-calling interface of the LMs.
  This means that you can run it with literally any model. When running in sandboxed environments you also don't need to take care
  of installing a single package — all it needs is bash.
- **Has a completely linear history** — every step of the agent just appends to the messages and that's it.
  So there's no difference between the trajectory and the messages that you pass on to the LM.
  Great for debugging & fine-tuning.
- **Executes actions with `subprocess.run`** — every action is completely independent (as opposed to keeping a stateful shell session running).
  This makes it trivial to execute the actions in sandboxes (literally just switch out `subprocess.run` with `docker exec`) and to
  scale up effortlessly. Seriously, this is [a big deal](https://mini-swe-agent.com/latest/faq/#why-no-shell-session), trust me.

This makes it perfect as a baseline system and for a system that puts the language model (rather than
the agent scaffold) in the middle of our attention.
You can see the result on the [SWE-bench (bash only)](https://www.swebench.com/) leaderboard, that evaluates the performance of different LMs with `mini`.

</details>

<details>
<summary>More motivation (as a tool)</summary>

Some agents are overfitted research artifacts. Others are UI-heavy frontend monsters.

The `mini` agent wants to be a hackable tool, not a black box.

- **Simple** enough to understand at a glance
- **Convenient** enough to use in daily workflows
- **Flexible** to extend

Unlike other agents (including our own [swe-agent](https://swe-agent.com/latest/)), it is radically simpler, because it:

- **Does not have any tools other than bash** — it doesn't even need to use the tool-calling interface of the LMs.
  Instead of implementing custom tools for every specific thing the agent might want to do, the focus is fully on the LM utilizing the shell to its full potential.
  Want it to do something specific like opening a PR?
  Just tell the LM to figure it out rather than spending time to implement it in the agent.
- **Executes actions with `subprocess.run`** — every action is completely independent (as opposed to keeping a stateful shell session running).
  This is [a big deal](https://mini-swe-agent.com/latest/faq/#why-no-shell-session) for the stability of the agent, trust me.
- **Has a completely linear history** — every step of the agent just appends to the messages that are passed to the LM in the next step and that's it.
  This is great for debugging and understanding what the LM is prompted with.

</details>

<details>
<summary>Should I use SWE-agent or mini-SWE-agent?</summary>

You should consider `mini-swe-agent` your default choice.
In particular, you should use `mini-swe-agent` if

- You want a quick command line tool that works locally
- You want an agent with a very simple control flow
- You want even faster, simpler & more stable sandboxing & benchmark evaluations
- You are doing FT or RL and don't want to overfit to a specific agent scaffold

You should use `swe-agent` if

- You want to experiment with different sets of tools, each with their own interface
- You want to experiment with different history processors

What you get with both

- Excellent performance on SWE-Bench
- A trajectory browser

</details>

<table>
<tr>
<td width="50%">
<a href="https://mini-swe-agent.com/latest/usage/mini/"><strong>CLI</strong></a> (<code>mini</code>)
</td>
<td>
<a href="https://mini-swe-agent.com/latest/usage/swebench/"><strong>Batch inference</strong></a>
</td>
</tr>
<tr>
<td width="50%">

![mini](https://github.com/SWE-agent/swe-agent-media/blob/main/media/mini/gif/mini.gif?raw=true)

</td>
<td>

![swebench](https://github.com/SWE-agent/swe-agent-media/blob/main/media/mini/gif/swebench.gif?raw=true)

</td>
</tr>
<tr>
<td>
<a href="https://mini-swe-agent.com/latest/usage/inspector/"><strong>Trajectory browser</strong></a>
</td>
<td>
<a href="https://mini-swe-agent.com/latest/advanced/cookbook/"><strong>Python bindings</strong></a>
</td>
</tr>
<tr>
<td>

![inspector](https://github.com/SWE-agent/swe-agent-media/blob/main/media/mini/gif/inspector.gif?raw=true)

</td>
<td>

```python
agent = DefaultAgent(
    LitellmModel(model_name=...),
    LocalEnvironment(),
)
agent.run("Write a sudoku game")
```

</td>
</tr>
</table>

## Let's get started!

**Option 1:** If you just want to try out the CLI (package installed in anonymous virtual environment)

```bash
pip install uv && uvx mini-swe-agent
# or
pip install pipx && pipx ensurepath && pipx run mini-swe-agent
```

**Option 2:** Install CLI & python bindings in current environment

```bash
pip install mini-swe-agent
mini  # run the CLI
```

**Option 3:** Install from source (developer setup)

```bash
git clone https://github.com/SWE-agent/mini-swe-agent.git
cd mini-swe-agent && pip install -e .
mini  # run the CLI
```

Read more in our [documentation](https://mini-swe-agent.com/latest/):

* [Quick start guide](https://mini-swe-agent.com/latest/quickstart/)
* [Using the `mini` CLI](https://mini-swe-agent.com/latest/usage/mini/)
* [Global configuration](https://mini-swe-agent.com/latest/advanced/global_configuration/)
* [Yaml configuration files](https://mini-swe-agent.com/latest/advanced/yaml_configuration/)
* [Power up with the cookbook](https://mini-swe-agent.com/latest/advanced/cookbook/)
* [FAQ](https://mini-swe-agent.com/latest/faq/)
* [Contribute!](https://mini-swe-agent.com/latest/contributing/)

## Attribution

If you found this work helpful, please consider citing the [SWE-agent paper](https://arxiv.org/abs/2405.15793) in your work:

```bibtex
@inproceedings{yang2024sweagent,
  title={{SWE}-agent: Agent-Computer Interfaces Enable Automated Software Engineering},
  author={John Yang and Carlos E Jimenez and Alexander Wettig and Kilian Lieret and Shunyu Yao and Karthik R Narasimhan and Ofir Press},
  booktitle={The Thirty-eighth Annual Conference on Neural Information Processing Systems},
  year={2024},
  url={https://arxiv.org/abs/2405.15793}
}
```

Our other projects:

<div align="center">
  <a href="https://github.com/SWE-agent/SWE-agent"><img src="https://raw.githubusercontent.com/SWE-agent/swe-agent-media/refs/heads/main/media/logos_banners/sweagent_logo_text_below.svg" alt="SWE-agent" height="120px"></a>
   &nbsp;&nbsp;
  <a href="https://github.com/SWE-agent/SWE-ReX"><img src="https://raw.githubusercontent.com/SWE-agent/swe-agent-media/refs/heads/main/media/logos_banners/swerex_logo_text_below.svg" alt="SWE-ReX" height="120px"></a>
   &nbsp;&nbsp;
  <a href="https://github.com/SWE-bench/SWE-bench"><img src="https://raw.githubusercontent.com/SWE-agent/swe-agent-media/refs/heads/main/media/logos_banners/swebench_logo_text_below.svg" alt="SWE-bench" height="120px"></a>
  &nbsp;&nbsp;
  <a href="https://github.com/SWE-bench/SWE-smith"><img src="https://raw.githubusercontent.com/SWE-agent/swe-agent-media/refs/heads/main/media/logos_banners/swesmith_logo_text_below.svg" alt="SWE-smith" height="120px"></a>
  &nbsp;&nbsp;
  <a href="https://github.com/codeclash-ai/codeclash"><img src="https://raw.githubusercontent.com/SWE-agent/swe-agent-media/refs/heads/main/media/logos_banners/codeclash_logo_text_below.svg" alt="CodeClash" height="120px"></a>
  &nbsp;&nbsp;
  <a href="https://github.com/SWE-bench/sb-cli"><img src="https://raw.githubusercontent.com/SWE-agent/swe-agent-media/refs/heads/main/media/logos_banners/sbcli_logo_text_below.svg" alt="sb-cli" height="120px"></a>
</div>
