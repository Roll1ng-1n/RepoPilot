"""Hidden host verifier; never copied into the task workspace."""

import sys
from pathlib import Path

sys.dont_write_bytecode = True
repository = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(repository / "src"))
from api import page
from store import slice_items

assert slice_items([1, 2, 3, 4], 2, 1) == [3]
assert page([1, 2, 3, 4, 5], 2, 2) == {"items": [3, 4], "total": 5}
assert page([1], 3, 2) == {"items": [], "total": 1}
for n, s in [(0, 2), (1, 0)]:
    try:
        page([], n, s)
    except ValueError:
        pass
    else:
        raise AssertionError("invalid pagination")

# Independent host-only cases and deterministic boundary checks.
for length in range(8):
    records = list(range(length))
    for size in range(1, 4):
        gathered = []
        for number in range(1, length + 3):
            result = page(records, number, size)
            assert result["total"] == length
            assert result["items"] == records[(number - 1) * size : number * size]
            gathered.extend(result["items"])
        assert gathered == records
