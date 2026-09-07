"""Hidden host verifier; never copied into the task workspace."""

import sys
from pathlib import Path

sys.dont_write_bytecode = True
repository = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(repository / "src"))
from feature import order

assert order(["1.10", "1.2", "1", "1.0", "2"]) == ["1", "1.0", "1.2", "1.10", "2"]
assert order([]) == []

# Independent host-only cases and deterministic boundary checks.
assert order(["10.0", "2.9", "2.10", "2.1.11", "2.1.9"]) == ["2.1.9", "2.1.11", "2.9", "2.10", "10.0"]
versions = ["1.0.0", "1", "1.0"]
assert order(versions) == versions
assert versions == ["1.0.0", "1", "1.0"]
