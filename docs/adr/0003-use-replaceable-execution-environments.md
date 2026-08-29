# Use replaceable execution environments

RepoPilot keeps its Runtime, Tools, State, and Trace independent of the execution backend. The CLI selects and injects an environment behind a minimal lifecycle-and-command-execution protocol, while Runtime interacts with it only through structured Tools; Local is the CLI default, Docker is explicit for repository work and the default for benchmarks. This trades mandatory isolation for usability while preserving one upper-layer control flow and a stable seam for future environment backends.
