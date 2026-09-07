"""Hidden host verifier; never copied into the task workspace."""

import sys
from pathlib import Path

sys.dont_write_bytecode = True
repository = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(repository / "src"))
from feature import materialize

assert (
    materialize(
        [{"op": "set", "key": "a", "value": 1}, {"op": "delete", "key": "a"}, {"op": "delete", "key": "absent"}]
    )
    == {}
)
assert materialize([{"op": "delete", "key": "a"}, {"op": "set", "key": "a", "value": None}]) == {"a": None}

# Independent host-only cases and deterministic boundary checks.
events = [
    {"op": "set", "key": "a", "value": 1},
    {"op": "set", "key": "b", "value": 2},
    {"op": "delete", "key": "a"},
    {"op": "set", "key": "a", "value": 3},
]
assert materialize(events) == {"a": 3, "b": 2}
assert materialize([]) == {}
assert events[0]["value"] == 1
