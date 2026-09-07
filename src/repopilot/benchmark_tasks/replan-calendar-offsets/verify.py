"""Hidden host verifier; never copied into the task workspace."""

import sys
from pathlib import Path

sys.dont_write_bytecode = True
repository = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(repository / "src"))
from feature import day

assert day("2025-01-01T00:30:00+02:00") == "2024-12-31"
assert day("2025-01-01T23:30:00-02:00") == "2025-01-02"
assert day("2025-01-01T12:00:00Z") == "2025-01-01"

# Independent host-only cases and deterministic boundary checks.
assert day("2024-03-01T00:00:00+00:30") == "2024-02-29"
assert day("2024-12-31T23:59:00-00:30") == "2025-01-01"
assert day("2024-02-29T13:04:05.123456Z") == "2024-02-29"
