"""Hidden host verifier; never copied into the task workspace."""

import sys
from pathlib import Path

sys.dont_write_bytecode = True
repository = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(repository / "src"))
from stats import summarize

assert summarize([]) == {"count": 0, "mean": None, "maximum": None}
assert summarize([-4, -2]) == {"count": 2, "mean": -3, "maximum": -2}
assert summarize([1, 2, 6]) == {"count": 3, "mean": 3, "maximum": 6}

# Additional host-only edge cases.
assert summarize([-9]) == {"count": 1, "mean": -9, "maximum": -9}
assert summarize([0, 0]) == {"count": 2, "mean": 0, "maximum": 0}

# Independent host-only cases and deterministic boundary checks.
for values in [[-100, -50, -25], [0], [1.5, 2.5], [4, 4, 4]]:
    assert summarize(values) == {"count": len(values), "mean": sum(values) / len(values), "maximum": max(values)}
