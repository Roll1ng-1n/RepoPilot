# Human approval and Git commits

RepoPilot evaluates each validated Tool Call before execution. Routine repository operations run automatically;
deletion, dependency installation, and Git writes pause the Agent Run in `WAITING_FOR_APPROVAL`. Use
`repopilot approve <run-id>` or `repopilot reject <run-id>` to resolve the persisted request. Rejection becomes a
Tool Observation so the model can revise its approach.

The dedicated `git_commit` Tool accepts a message, reason, and explicit repository paths. After approval, its commit
hash and reason are recorded in the Trace, metadata, and task report. Push, rebase, reset, and Pull Request operations
are unsupported in V1. An explicitly disposable Docker benchmark can opt into automatic approval with
`--auto-approve-disposable-docker-benchmark`.

## Known limitations

- Risk classification is a small best-effort recognizer, not a shell parser or security boundary. General commands
  remain an escape hatch, as documented in the V1 design.
- The automatic-approval flag verifies Docker selection but cannot independently prove that the caller's repository
  or container is disposable.
- Approval resolves one high-risk Tool Call at a time. Remaining calls from the same model turn are checkpointed and
  resume only after that decision.
- Local commit success depends on the Target Repository's Git configuration. Failures return a correction
  Observation and do not produce commit metadata.
