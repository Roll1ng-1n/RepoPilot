from aggregate import aggregate
from decode import decode
from normalize import normalize
from render import render
from selection import select
from validate import validate


def run(data):
    result = data
    result = decode(result)
    result = validate(result)
    result = normalize(result)
    result = aggregate(result)
    result = select(result)
    return render(result)
