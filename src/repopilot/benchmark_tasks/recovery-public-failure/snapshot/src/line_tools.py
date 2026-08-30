"""Small line-cleaning utility used by the Recovery benchmark task."""

from collections.abc import Iterable


def unique_clean_lines(lines: Iterable[str]) -> list[str]:
    """Return non-empty, trimmed lines without exact duplicates."""

    seen: set[str] = set()
    result: list[str] = []
    for line in lines:
        value = line.strip()
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result
