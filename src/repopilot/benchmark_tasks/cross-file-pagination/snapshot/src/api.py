from store import slice_items


def page(items, number, page_size):
    return {"items": slice_items(items, number, page_size), "total": page_size}
