"""Hidden host verifier; never copied into the task workspace."""

import sys
from pathlib import Path

sys.dont_write_bytecode = True
repository = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(repository / "src"))
from intervals import merge

a = [[5, 7], [1, 3], [3, 6], [9, 10]]
assert merge(a) == [[1, 7], [9, 10]]
assert a == [[5, 7], [1, 3], [3, 6], [9, 10]]
assert merge([]) == []
assert merge([[1, 10], [2, 3]]) == [[1, 10]]

# Independent host-only cases and deterministic boundary checks.
from itertools import permutations

for intervals in permutations([[0, 2], [5, 9], [1, 6], [12, 12]]):
    assert merge(list(intervals)) == [[0, 9], [12, 12]]
assert merge([[-9, -8], [-3, -1]]) == [[-9, -8], [-3, -1]]
