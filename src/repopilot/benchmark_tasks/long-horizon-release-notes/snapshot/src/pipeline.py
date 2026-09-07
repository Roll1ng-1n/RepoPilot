from decode import decode
from deduplicate import deduplicate
from normalize import normalize
from render import render
from selection import select
from validate import validate


def run(data):
    result = data
    result = decode(result)
    result = validate(result)
    result = normalize(result)
    result = select(result)
    result = deduplicate(result)
    return render(result)
