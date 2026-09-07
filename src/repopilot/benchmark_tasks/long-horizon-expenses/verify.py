"""Hidden host verifier; never copied into the task workspace."""

import sys
from pathlib import Path

sys.dont_write_bytecode = True
repository = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(repository / "src"))
from pipeline import run

assert run("owner,amount\n Bob ,1.005\nbob,2.00\nAda,-1\nX,no\nY,NaN\nZ,0\n,5\n") == "bob:3.01"
assert run("owner,amount\n") == ""

# Independent host-only cases and deterministic boundary checks.
assert run("owner,amount\n A ,0.10\na,0.20\nB,5\nb,-5\n") == "a:0.30"
assert run("owner,amount\nZ,1.015\nA,2.005\n") == "a:2.01\nz:1.02"
assert run("owner,amount\nA,-1\n") == ""
