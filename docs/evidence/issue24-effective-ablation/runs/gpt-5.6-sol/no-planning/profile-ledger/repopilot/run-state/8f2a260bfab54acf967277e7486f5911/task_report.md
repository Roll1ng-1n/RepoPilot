# Task report

## Root cause

normalize_key returned keys unchanged and report always returned an empty string, so normalization, aggregation, rounding, ordering, and rendering were absent.

## Changes

- Implemented normalize_key in src/ledger/normalize.py using strip() followed by Unicode-aware casefold().
- Implemented report in src/ledger/report.py to skip empty normalized keys, parse amounts with Decimal from strings, aggregate by normalized key, round totals HALF_UP to two decimal places, sort keys ascending, and return rendered text.

## Rationale

The implementation now follows the configuration contract and scoped ledger instructions without changing configuration, checks, documentation, or AGENTS.md files.
## Verification

- `Repository checks`: Run the configured test entry from pyproject.toml to verify normalization, aggregation, rounding, skipping empty keys, and output rendering. (passed)

## Risks

- No additional risks identified; behavior is covered by the configured test suite.

## Git commits

- No local Git Commits were created.

## Completion decision

```json
{
  "fingerprint": "a323de0e663f7cf0539a1c4bb52194ba8d4dfd5da49d15c343174052b865d7f2",
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
