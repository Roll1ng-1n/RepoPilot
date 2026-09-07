"""Hidden host verifier; never copied into the task workspace."""

import sys
from pathlib import Path

sys.dont_write_bytecode = True
repository = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(repository / "src"))
from clamp import clamp

assert [clamp(v, 0, 10) for v in [-2, 0, 4.5, 10, 20]] == [0, 0, 4.5, 10, 10]
try:
    clamp(2, 5, 1)
except ValueError:
    pass
else:
    raise AssertionError("reversed bounds accepted")

# Independent host-only cases and deterministic boundary checks.
for low, high in [(-7, -2), (3, 3), (-2.5, 4.5)]:
    for value in [low - 1, low, (low + high) / 2, high, high + 1]:
        result = clamp(value, low, high)
        assert low <= result <= high
        assert result == (low if value < low else high if value > high else value)
