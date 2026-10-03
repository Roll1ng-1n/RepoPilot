# Task report

## Root cause

TTLCache.expire used a strict `time > expires` comparison, so entries remained in the cache when cleanup ran exactly at their expiration timestamp.

## Changes

- Changed `TTLCache.expire` to remove entries when `time >= curr.expires`.
- Kept the existing expiration ordering and `(key, value)` collection behavior, preserving unexpired entries and public APIs.

## Rationale

The cache's lookup and membership paths already treat the expiration boundary as expired. Aligning expire() with that contract fixes exact-boundary cleanup without affecting other cache classes.
## Verification

- `Baseline required test suite before editing`: Establish the pre-change repository test status as requested. (failed)
- `Full checks suite after the TTLCache.expire source fix.`: Verify TTLCache expires entries at the exact TTL boundary, returns removed pairs, retains unexpired entries, and preserves the rest of the library behavior. (passed)

## Risks

- No risks reported.

## Git commits

- No local Git Commits were created.

## Completion decision

```json
{
  "fingerprint": "ad915ccd6bc1d66db997e063bf2d4676d117a46d248556ced06b5944a85254b4",
  "required_verifications": [],
  "evidence_scope": "model_selected_checks",
  "covered_plan_steps": [
    "complete-task"
  ],
  "problems": [],
  "completion_allowed": true,
  "verification_sequences": [
    2
  ]
}
```
