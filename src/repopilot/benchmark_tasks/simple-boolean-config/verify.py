"""Hidden host verifier; never copied into the task workspace."""

import sys
from pathlib import Path

sys.dont_write_bytecode = True
repository = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(repository / "src"))
from config import parse_bool

for value in ["TRUE", " 1 ", "Yes", "on"]:
    assert parse_bool(value) is True
for value in ["false", "0", " NO ", "OFF"]:
    assert parse_bool(value) is False
for value in ["", "maybe", "2"]:
    try:
        parse_bool(value)
    except ValueError:
        pass
    else:
        raise AssertionError(value)

# Independent host-only cases and deterministic boundary checks.
for token, expected in [
    ("true", True),
    ("1", True),
    ("yes", True),
    ("on", True),
    ("false", False),
    ("0", False),
    ("no", False),
    ("off", False),
]:
    for variant in [token, token.upper(), "\t" + token + "\n"]:
        assert parse_bool(variant) is expected
