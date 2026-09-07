from schema import fields


def render(rows):
    return "\n".join(",".join(row[k] for k in fields) for row in rows)
