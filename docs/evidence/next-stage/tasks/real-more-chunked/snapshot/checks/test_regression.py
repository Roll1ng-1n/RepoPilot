import sys
from pathlib import Path
import unittest

class Regression(unittest.TestCase):
    def test_regression(self):
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
