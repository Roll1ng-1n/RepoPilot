import sys, hashlib
from pathlib import Path
sys.dont_write_bytecode = True
root = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(root))
sys.path.insert(0, str(root / 'src'))
assert hashlib.sha256((root / 'checks/test_regression.py').read_bytes()).hexdigest() == 'dde6b7876faba5ec28c79e8a55c1a71759d3bcab99e2f8d3f7d7caef93f0b26c'
from cachetools import TTLCache
clock = [0.0]
cache = TTLCache(10, ttl=2, timer=lambda: clock[0])
cache['first'] = 1
clock[0] = 1
cache['second'] = 2
clock[0] = 2
assert list(cache.expire()) == [('first', 1)]
assert cache['second'] == 2
clock[0] = 3
assert list(cache.expire()) == [('second', 2)]
assert list(cache.expire()) == []
