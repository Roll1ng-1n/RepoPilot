# Context strategies

RepoPilot controls the history sent to the model with `--context-strategy none`, `sliding_window`, or `summary`.
`--context-max-characters` sets the approximate serialized-message threshold used by the latter two strategies.
The Runtime still writes the complete Agent Run events to `trace.jsonl` and the complete message history to the
Checkpoint.

`sliding_window` keeps the task, current Plan, facts recorded through `record_fact`, and as many complete recent
Agent Steps as fit. `summary` asks the configured model to compress older Agent Steps into structured facts,
completed work, decisions, and open questions. A failed summary request records a Trace event and permanently falls
back to `sliding_window` for that Agent Run. Context strategy state is restored by `resume`.

## Known limitations

- The threshold counts serialized characters, not provider-specific tokens, and is not a hard model context limit.
- RepoPilot never splits the most recent Agent Step. Its anchors and newest complete Step can therefore exceed the
  configured threshold; only older Steps are eligible for removal or summarization.
- Important facts are explicit: the model must call `record_fact` for a fact that must survive every later window.
- Summary uses the configured execution model and expects one JSON object. Provider errors or malformed output use
  the documented sliding-window fallback instead of retrying summary compression.
