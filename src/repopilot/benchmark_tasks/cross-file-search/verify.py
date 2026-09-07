"""Hidden host verifier; never copied into the task workspace."""

import sys
from pathlib import Path

sys.dont_write_bytecode = True
repository = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(repository / "src"))
from index import build_index
from search import search

r = [{"id": 2, "text": "Red red Fox"}, {"id": 1, "text": "red bird"}, {"id": 3, "text": "FOX"}]
assert build_index(r)["red"] == {1, 2}
assert search(r, " RED fox ") == [2]
assert search(r, "fox") == [2, 3]
assert search(r, "") == []
assert search(r, "missing") == []

# Independent host-only cases and deterministic boundary checks.
records = [{"id": 9, "text": "Straße   blue"}, {"id": 4, "text": "STRASSE green"}]
assert search(records, " strasse ") == [4, 9]
assert search(records, "blue blue") == [9]
assert search(records, "green missing") == []
assert search([], "anything") == []
assert records[0]["text"] == "Straße   blue"
