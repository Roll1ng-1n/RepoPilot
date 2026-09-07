def normalize(rows):
    return [(r["sku"], r["delta"]) for r in rows]
