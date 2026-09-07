from money import amount


def quote(items, tax_rate):
    return str(sum(amount(i["price"]) for i in items))
