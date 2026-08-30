"""Small text utility used by the single-file seed task."""


def slugify(value: str) -> str:
    """Return a lower-case hyphen-separated representation of a title."""

    return "-".join(value.strip().lower().split(" "))
