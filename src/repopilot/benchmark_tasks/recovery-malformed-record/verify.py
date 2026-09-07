"""Hidden host verifier; never copied into the task workspace."""

import sys
from pathlib import Path

sys.dont_write_bytecode = True
repository = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(repository / "src"))
from records import parse_rows

assert parse_rows("# config\na = 1\nbad\n\nb=2=3\na=4") == {"a": "4", "b": "2=3"}
assert parse_rows("") == {}

# Additional host-only edge cases.
assert parse_rows("x=\n #ignore=3\ny=a=b=c\ninvalid\nx=last") == {"x": "last", "y": "a=b=c"}

# Independent host-only cases and deterministic boundary checks.
for value in ["", "a=b", "王", "#literal"]:
    assert parse_rows("x = old\nmalformed\n # comment\nx = " + value + "\ny = tail") == {"x": value, "y": "tail"}
