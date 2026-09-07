"""Hidden host verifier; never copied into the task workspace."""

import sys
from pathlib import Path

sys.dont_write_bytecode = True
repository = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(repository / "src"))
import csv
import io

from export import render
from schema import fields

assert fields == ["name", "note"]
rows = [{"name": "王", "note": 'a,b\nc"d'}]
assert list(csv.DictReader(io.StringIO(render(rows)))) == rows
assert render([]) == "name,note\n"

# Independent host-only cases and deterministic boundary checks.
rows = [{"name": "", "note": ""}, {"name": "a,b", "note": "line1\nline2"}, {"name": '"quote"', "note": "尾"}]
output = render(rows)
assert output.startswith("name,note\n")
assert "\r\n" not in output
assert list(csv.DictReader(io.StringIO(output))) == rows
assert output.endswith("\n")
