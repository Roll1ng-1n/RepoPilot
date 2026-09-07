"""Hidden host verifier; never copied into the task workspace."""

import sys
from pathlib import Path

sys.dont_write_bytecode = True
repository = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(repository / "src"))
from decimal import Decimal

from checkout import quote
from money import amount

assert amount("0.1") == Decimal("0.1")
assert quote([{"price": "0.10", "quantity": 3}], "0.05") == "0.32"
assert quote([], "0.1") == "0.00"
assert quote([{"price": "10", "quantity": 2}, {"price": "1.25", "quantity": 4}], "0.2") == "30.00"

# Independent host-only cases and deterministic boundary checks.
items = [{"price": "1.005", "quantity": 2}, {"price": "3.10", "quantity": 0}]
assert quote(items, "0") == "2.01"
assert items == [{"price": "1.005", "quantity": 2}, {"price": "3.10", "quantity": 0}]
assert quote([{"price": "-2.05", "quantity": 2}], "0.1") == "-4.51"
