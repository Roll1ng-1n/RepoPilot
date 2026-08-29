# Upstream provenance

## mini-SWE-agent v2.4.6

RepoPilot begins from the following fixed mini-SWE-agent source snapshot:

- Official repository: <https://github.com/SWE-agent/mini-swe-agent>
- Official release and tag: <https://github.com/SWE-agent/mini-swe-agent/releases/tag/v2.4.6>
- Upstream commit: `a83fcae82d2a08f0ee0c688f9d137b3566c097f8`
- Source license: MIT, retained verbatim in [LICENSE.md](LICENSE.md).

## Import strategy

The initial baseline is the Git archive of the `v2.4.6` tag at the commit above.
It contains 219 upstream-tracked files imported without content changes. Root-level
`AGENTS.md` and `CLAUDE.md` were deliberately not imported: RepoPilot's own
repository instructions must remain authoritative. RepoPilot's existing
`AGENTS.md`, `CONTEXT.md`, `project.md`, and `docs/agents/` and `docs/adr/`
content were retained; non-conflicting upstream documentation was added under
`docs/`.

This repository does not promise automatic compatibility with later
mini-SWE-agent releases. The `minisweagent` package remains the identifiable
upstream base. RepoPilot-specific capabilities belong in a separate
`repopilot` package unless an upstream interface blocks a reasonable extension.

## Capabilities already present in the baseline

The import already supplies the mini-SWE-agent CLI and Python package, default
and interactive agents, LiteLLM/OpenAI-compatible model integrations, and
native tool-call action handling. It also includes local, Docker, and optional
execution environments; bounded step, cost, and wall-time controls; model API
retry support; interactive confirmation; trajectory saving and inspection; and
SWE-bench and ProgramBench runners. These are inherited capabilities, not
RepoPilot additions.

## Verification

The following commands passed on Python 3.12 in an isolated temporary virtual
environment. `MSWEA_GLOBAL_CONFIG_DIR` was a temporary directory, so the checks
did not create or modify a user's mini-SWE-agent configuration.

```console
MSWEA_GLOBAL_CONFIG_DIR=<temporary-dir> mini --help
MSWEA_GLOBAL_CONFIG_DIR=<temporary-dir> python -m minisweagent --help
MSWEA_GLOBAL_CONFIG_DIR=<temporary-dir> python -m compileall -q src
MSWEA_GLOBAL_CONFIG_DIR=<temporary-dir> python -m pytest -q \
  tests/models/test_actions_toolcall.py \
  tests/agents/test_init.py \
  tests/run/test_cli_integration.py \
  tests/test_init.py \
  --deselect='tests/run/test_cli_integration.py::test_mini_extra_subcommand_help[swebench-single-aliases3]'
```

Both CLI help commands and the compilation check exited successfully. The test
command completed with **45 passed, 1 deselected**. The deselected help test
imports `datasets` through the `swebench-single` command. The full upstream
suite was intentionally not run in this baseline verification because this
temporary environment excludes `datasets` and its large `pandas`/`pyarrow`
dependency chain; it is not reported as a passing result.
