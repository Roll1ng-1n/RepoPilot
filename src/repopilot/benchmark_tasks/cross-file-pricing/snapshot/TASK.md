Repair quote(items, tax_rate) across money.py and checkout.py: use Decimal amounts, sum quantity times price, apply tax once, round HALF_UP to two decimals and return a string. Do not mutate items.
