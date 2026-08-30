# Task report

## Root cause

The original implementation split on literal single spaces (split(\" \")), which failed to collapse runs of multiple spaces/tabs/newlines into one hyphen and could leave embedded whitespace or produce double hyphens. Additionally, strip() only removed edge whitespace but didn't help interior runs.

## Changes

- Changed src/slugify.py to use value.lower().split() instead of value.strip().lower().split(" "), so str.split() with no separator collapses any run of whitespace (spaces, tabs, newlines) into single tokens, ignores leading/trailing whitespace, returns [] for whitespace-only input (joining to an empty string), and leaves punctuation intact.

## Rationale

Using split() without an argument is the idiomatic fix: it splits on arbitrary runs of whitespace, trims leading/trailing whitespace implicitly, and yields an empty list for whitespace-only strings, satisfying all four requirements while preserving punctuation.
## Verification

- `src/slugify.py slugify behavior`: Verify leading/trailing whitespace is ignored, whitespace runs become one hyphen, whitespace-only returns empty string, and punctuation is preserved. (passed)

## Risks

- Behavior now also collapses tabs/newlines (broader than just spaces), which matches the 'every run of whitespace' requirement. Punctuation remains preserved as-is.

## Git commits

- No local Git Commits were created.
