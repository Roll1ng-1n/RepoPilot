import sys

sys.path.insert(0, "src")
from collect import collect

assert collect("local://data") == {"url": "local://data", "timeout": 5}
assert collect("local://other", 9) == {"url": "local://other", "timeout": 9}
