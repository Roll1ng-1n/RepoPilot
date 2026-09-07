"""Hidden host verifier; never copied into the task workspace."""

import sys
from pathlib import Path

sys.dont_write_bytecode = True
repository = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(repository / "src"))
from collect import collect

assert collect("local://data") == {"url": "local://data", "timeout": 5}
assert collect("local://other", 9) == {"url": "local://other", "timeout": 9}

# Additional host-only edge cases.
assert collect("local://empty", 0) == {"url": "local://empty", "timeout": 0}

# Independent host-only cases and deterministic boundary checks.
for url in ["local://a", "local://unicode/王", "local://b?x=2"]:
    for timeout in [1, 2.5, 30]:
        assert collect(url, timeout) == {"url": url, "timeout": timeout}
