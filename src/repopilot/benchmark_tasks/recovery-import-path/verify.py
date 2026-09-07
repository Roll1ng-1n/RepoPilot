"""Hidden host verifier; never copied into the task workspace."""

import sys
from pathlib import Path

sys.dont_write_bytecode = True
repository = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(repository / "src"))
from loader import load

assert load(" 3, -1, 5 ") == [3, -1, 5]
assert load("0") == [0]

# Additional host-only edge cases.
assert load(" -10, 0, 200 ") == [-10, 0, 200]

# Independent host-only cases and deterministic boundary checks.
for values in [[-31], [12, 0, -4, 88], [7, 7, 7]]:
    assert load(" , ".join(map(str, values))) == values
