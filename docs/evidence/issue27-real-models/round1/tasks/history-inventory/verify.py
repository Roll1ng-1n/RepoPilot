import sys,json,hashlib,copy
from pathlib import Path
root=Path(sys.argv[1]);sys.dont_write_bytecode=True;sys.path.insert(0,str(root))
from src.inventory.pipeline import reconcile
from src.inventory.validate import validate
from src.inventory.aggregate import aggregate
from src.inventory.select import select
from src.inventory.normalize import normalize
values=[{"sku":" Straße ","delta":3},{"sku":"STRASSE","delta":-1},{"sku":"z","delta":True},{"sku":"a","delta":-3},{"sku":" ","delta":8},{"sku":"a","delta":3},{"sku":"k","delta":1.2},None]
assert reconcile(json.dumps(values))=="strasse=2"
assert reconcile("not json")==""
assert reconcile("{}") == ""
a=[{"sku":" A ","delta":2,"extra":1}];before=copy.deepcopy(a)
assert validate(a)==[{"sku":" A ","delta":2}];assert a==before
assert normalize(a)==[{"sku":"a","delta":2}];assert a==before
assert aggregate([{"sku":"x","delta":1},{"sku":"x","delta":-1}])=={"x":0}
b={"x":0,"y":-2};assert select(b)=={"y":-2};assert b=={"x":0,"y":-2}
for name,digest in json.loads((Path(__file__).parent/'protected.json').read_text()).items():
    assert hashlib.sha256((root/name).read_bytes()).hexdigest()==digest,name
print('hidden checks passed')
