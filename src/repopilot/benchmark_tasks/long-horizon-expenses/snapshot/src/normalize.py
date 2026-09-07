def normalize(rows):
    return [(r["owner"], r["amount"]) for r in rows]
