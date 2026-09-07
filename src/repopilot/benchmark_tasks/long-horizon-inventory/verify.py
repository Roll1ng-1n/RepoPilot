"""Hidden host verifier; never copied into the task workspace."""

import sys
from pathlib import Path

sys.dont_write_bytecode = True
repository = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(repository / "src"))
import json

from pipeline import run

assert (
    run(
        json.dumps(
            [
                {"sku": " B ", "delta": 3},
                {"sku": "b", "delta": -1},
                {"sku": "A", "delta": -2},
                {"sku": "z", "delta": 0},
                {"sku": "bad", "delta": True},
                {"sku": "", "delta": 1},
            ]
        )
    )
    == "a=-2\nb=2"
)
assert run("[]") == ""

# Independent host-only cases and deterministic boundary checks.
for delta in [-7, 1, 13]:
    records = [
        {"sku": " X ", "delta": delta},
        {"sku": "x", "delta": delta},
        {"sku": "drop", "delta": 4},
        {"sku": "drop", "delta": -4},
    ]
    assert run(json.dumps(records)) == f"x={2 * delta}"
assert run(json.dumps([{"sku": None, "delta": 2}, {"sku": "q", "delta": "2"}])) == ""
