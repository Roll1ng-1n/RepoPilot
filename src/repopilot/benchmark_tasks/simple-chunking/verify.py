"""Hidden host verifier; never copied into the task workspace."""

import sys
from pathlib import Path

sys.dont_write_bytecode = True
repository = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(repository / "src"))
from chunks import chunks

a = [1, 2, 3, 4, 5]
assert chunks(a, 2) == [[1, 2], [3, 4], [5]]
assert a == [1, 2, 3, 4, 5]
assert chunks([], 3) == []
assert chunks((1, 2), 5) == [[1, 2]]
for size in [0, -1]:
    try:
        chunks(a, size)
    except ValueError:
        pass
    else:
        raise AssertionError("invalid size")

# Independent host-only cases and deterministic boundary checks.
for length in range(11):
    for size in range(1, 6):
        source = list(range(length))
        result = chunks(source, size)
        assert [v for chunk in result for v in chunk] == source
        assert all(len(chunk) == size for chunk in result[:-1])
        assert not result or 0 < len(result[-1]) <= size
        if result:
            result[0].append(99)
            assert source == list(range(length))
