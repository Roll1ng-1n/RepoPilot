import sys

sys.path.insert(0, "src")
from records import parse_rows

assert parse_rows("# config\na = 1\nbad\n\nb=2=3\na=4") == {"a": "4", "b": "2=3"}
assert parse_rows("") == {}
