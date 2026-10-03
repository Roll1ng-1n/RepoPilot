import unittest,json
from src.inventory.pipeline import reconcile
class Checks(unittest.TestCase):
    def test_pipeline(self):
        self.assertEqual(reconcile(json.dumps([{"sku":" B ","delta":2},{"sku":"b","delta":-1},{"sku":"A","delta":-2}])), "a=-2\nb=1")
    def test_empty(self):
        self.assertEqual(reconcile("[]"), "")
