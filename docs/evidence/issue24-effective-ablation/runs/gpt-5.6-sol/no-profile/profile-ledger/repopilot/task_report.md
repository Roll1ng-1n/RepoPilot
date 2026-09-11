# Task report

## Root cause

normalize_key was a pass-through and report returned an empty string, so the configured normalization, aggregation, rounding, filtering, ordering, and rendering behavior was missing.

## Changes

- Implemented Unicode-aware key normalization with strip() followed by casefold().
- Implemented Decimal-based aggregation, skipping empty normalized keys, HALF_UP rounding to two decimal places, ascending normalized-key ordering, and rendered string output.
- Changed only src/ledger/normalize.py and src/ledger/report.py.

## Rationale

The implementation now follows the pyproject.toml configuration contract and scoped src/ledger instructions without modifying configuration, checks, documentation, or instruction files.
## Verification

- `The configured unittest discovery suite in checks`: Run the test command documented in pyproject.toml after implementing normalize_key and report. (passed)

## Risks

- No risks reported.

## Git commits

- No local Git Commits were created.

## Completion decision

```json
{
  "fingerprint": "8145021e22f20859375856e9367bffb4b8a9e18ad7fd1542fcfc4bc6b7d06599",
  "required_verifications": [],
  "evidence_scope": "model_selected_checks",
  "covered_plan_steps": [
    "complete-task"
  ],
  "problems": [],
  "completion_allowed": true,
  "verification_sequences": [
    1
  ]
}
```
