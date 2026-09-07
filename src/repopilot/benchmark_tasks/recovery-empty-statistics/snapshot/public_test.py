import sys

sys.path.insert(0, "src")
from stats import summarize

assert summarize([]) == {"count": 0, "mean": None, "maximum": None}
assert summarize([-4, -2]) == {"count": 2, "mean": -3, "maximum": -2}
assert summarize([1, 2, 6]) == {"count": 3, "mean": 3, "maximum": 6}
