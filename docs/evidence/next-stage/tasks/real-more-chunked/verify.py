import sys, hashlib
from pathlib import Path
sys.dont_write_bytecode = True
root = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(root))
assert hashlib.sha256((root / 'checks/test_regression.py').read_bytes()).hexdigest() == '970b5c9301b605d060aee1ad363c1422662aaeb7718b6733c8488e151c38d5a5'
from more_itertools import chunked
from more_itertools.recipes import take
assert take(2, range(4)) == [0, 1]
assert list(chunked(range(5), 2)) == [[0, 1], [2, 3], [4]]
assert list(chunked(range(4), 2, strict=True)) == [[0, 1], [2, 3]]
try:
    list(chunked(range(5), 2, strict=True))
except ValueError:
    pass
else:
    raise AssertionError('strict chunked must reject remainder')
