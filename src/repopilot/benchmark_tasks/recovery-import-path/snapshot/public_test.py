import sys

sys.path.insert(0, "src")
from loader import load

assert load(" 3, -1, 5 ") == [3, -1, 5]
assert load("0") == [0]
