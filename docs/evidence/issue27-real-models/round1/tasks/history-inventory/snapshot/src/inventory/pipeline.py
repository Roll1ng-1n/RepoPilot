from .parse import parse
from .validate import validate
from .normalize import normalize
from .aggregate import aggregate
from .select import select
from .render import render

def reconcile(text: str) -> str:
    return render(select(aggregate(normalize(validate(parse(text))))))
