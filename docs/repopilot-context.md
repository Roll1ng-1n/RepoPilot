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
- Strategy selection retains complete recent steps. The hard request bound may compact large observations, evict older completed steps, or trim completed call/result pairs from a large batch. It preserves instructions, task, plan and bounded historical tool receipts; it never retains orphaned tool results. The size bound counts the full serialized request envelope conservatively, rather than provider-specific token estimates.
- Important facts are explicit: the model must call `record_fact` for a fact that must survive every later window.
- Summary uses the configured execution model and expects one JSON object. Provider errors or malformed output use
  the documented sliding-window fallback instead of retrying summary compression.

## Exploration and saved history

The bounded ProgressTracker observes completed read_file/search_code/list_files calls and detects length 1–4 cycles repeated at least three times. File changes and new verification evidence reset the observation segment. Use --no-progress-detection for explicit ablation; resume retains the setting. Trace exploration_loop_detected records the source calls. See [metrics](evidence/next-stage/metrics.md) and [fixed evaluation](evidence/next-stage/report.md).

Schema 3 saves large redacted immutable texts in objects/ and restores full history when reading checkpoints. Preserve the complete run directory; see [format and recovery](evidence/next-stage/performance/report.md).
