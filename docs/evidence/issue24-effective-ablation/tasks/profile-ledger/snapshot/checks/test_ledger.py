import unittest
from src.ledger.report import report
class Checks(unittest.TestCase):
    def test_report(self):
        self.assertEqual(report([(" A ","1.005"),("a","1.005"),("B","-0.005")]), "a=2.01\nb=-0.01")
    def test_unicode(self):
        self.assertEqual(report([(" Straße ","1"),("STRASSE","2"),(" ","99")]), "strasse=3.00")
