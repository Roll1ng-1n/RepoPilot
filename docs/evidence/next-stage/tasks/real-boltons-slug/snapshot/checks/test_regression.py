import sys
from pathlib import Path
import unittest

class Regression(unittest.TestCase):
    def test_regression(self):
        from boltons.strutils import slugify
        assert slugify('Hello, World!', delim='-') == 'hello-world'
        assert slugify('Hello World', delim='::', lower=False) == 'Hello::World'
        assert slugify('') == ''
        assert slugify('Café Noir', delim='-', ascii=True) == b'cafe-noir'
