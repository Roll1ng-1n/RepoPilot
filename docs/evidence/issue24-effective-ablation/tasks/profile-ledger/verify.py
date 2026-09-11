import sys,json,hashlib
from pathlib import Path
root=Path(sys.argv[1]);sys.dont_write_bytecode=True;sys.path.insert(0,str(root))
from src.ledger.report import report
from src.ledger.normalize import normalize_key
assert normalize_key(" Straße ")=="strasse"
assert report([])==""
assert report([("b","-0.005"),(" A ","0.005"),("a","0.005"),(" ","99")])=="a=0.01\nb=-0.01"
assert report([("X","999999999999.015"),("x","0.005")])=="x=999999999999.02"
assert report([("Straße","2"),("STRASSE","1")])=="strasse=3.00"
for name,digest in json.loads((Path(__file__).parent/'protected.json').read_text()).items():
    assert hashlib.sha256((root/name).read_bytes()).hexdigest()==digest,name
print('hidden checks passed')
