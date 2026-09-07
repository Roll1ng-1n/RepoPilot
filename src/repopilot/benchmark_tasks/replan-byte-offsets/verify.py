"""Hidden host verifier; never copied into the task workspace."""

import sys
from pathlib import Path

sys.dont_write_bytecode = True
repository = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(repository / "src"))
from feature import locate

assert locate("王🙂abc", "a") == 7
assert locate("abc", "b") == 1
assert locate("王", "x") == -1
assert locate("王", "") == 0

# Independent host-only cases and deterministic boundary checks.
for prefix in ["", "é", "汉字", "🙂é", "abc"]:
    assert locate(prefix + "needle" + prefix, "needle") == len(prefix.encode("utf-8"))
assert locate("éxé", "é") == 0
