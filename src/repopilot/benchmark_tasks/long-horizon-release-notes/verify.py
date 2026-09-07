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
                {"kind": "FIX", "title": " Crash "},
                {"kind": "feat", "title": "API"},
                {"kind": "fix", "title": "Crash"},
                {"kind": "chore", "title": "Build"},
                {"kind": "feat", "title": ""},
                {"kind": 1, "title": "bad"},
            ]
        )
    )
    == "feat: API\nfix: Crash"
)
assert run("[]") == ""

# Independent host-only cases and deterministic boundary checks.
records = [
    {"kind": "fix", "title": "Z"},
    {"kind": "feat", "title": "B"},
    {"kind": "feat", "title": "A"},
    {"kind": "fix", "title": "A"},
    {"kind": "feat", "title": "A"},
]
assert run(json.dumps(records)) == "feat: B\nfeat: A\nfix: Z\nfix: A"
assert run(json.dumps([{"kind": "docs", "title": "Only docs"}])) == ""
assert (
    run(json.dumps([{"kind": " FEAT ", "title": " Trim title "}, {"kind": "FIX", "title": " Unicode 王 "}]))
    == "feat: Trim title\nfix: Unicode 王"
)
