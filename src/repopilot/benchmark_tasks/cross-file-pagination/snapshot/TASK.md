Fix the API pagination contract across store.py and api.py: page numbers are one-based; page_size must be positive; return items and total before slicing; invalid page/page_size raise ValueError.
