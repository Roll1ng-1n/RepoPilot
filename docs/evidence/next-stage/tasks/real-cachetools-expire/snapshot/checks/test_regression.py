import sys
from pathlib import Path
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

class Regression(unittest.TestCase):
    def test_regression(self):
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
