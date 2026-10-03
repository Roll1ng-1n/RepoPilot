import sys, hashlib
from pathlib import Path
sys.dont_write_bytecode = True
root = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(root))
assert hashlib.sha256((root / 'checks/test_regression.py').read_bytes()).hexdigest() == '4a0551243ba45b50bb6b0f3dee71b8e1d2b85b0eeefd171934695d3cc6d55c61'
from boltons.strutils import slugify
assert slugify('Hello, World!', delim='-') == 'hello-world'
assert slugify('Hello World', delim='::', lower=False) == 'Hello::World'
assert slugify('') == ''
assert slugify('Café Noir', delim='-', ascii=True) == b'cafe-noir'
