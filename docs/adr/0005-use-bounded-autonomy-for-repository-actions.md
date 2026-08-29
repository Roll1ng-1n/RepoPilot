# Use bounded autonomy for repository actions

RepoPilot automatically performs low- and medium-risk repository work but requires Human Approval for destructive operations, dependency installation, and Git writes. V1 uses a lightweight best-effort risk policy rather than a comprehensive security analyzer; disposable Docker benchmarks may opt into automatic approval, while the product exposes local `git_commit` only through approval and does not support push, rebase, reset, or pull-request creation.
