"""Hidden host verifier; never copied into the task workspace."""

import sys
from pathlib import Path

sys.dont_write_bytecode = True
repository = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(repository / "src"))
from pipeline import run

assert run("get /a 404\nGET /b 500\npost /c 403\nGET /ok 200\nbroken\nGET /bad NaN") == "GET:2\nPOST:1"
assert run("") == ""

# Independent host-only cases and deterministic boundary checks.
assert run("put /a 399\nPUT /b 400\nput /c 599\nGET /a 201\nmalformed too many fields here") == "PUT:2"
assert run("GET / 200\nPOST / 201") == ""
assert run("patch /x 404\nDELETE /y 500") == "DELETE:1\nPATCH:1"
