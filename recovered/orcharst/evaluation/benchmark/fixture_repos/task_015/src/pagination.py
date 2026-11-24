def paginate(items: list, page: int, size: int) -> list:
    if page < 1 or size < 1:
        raise ValueError("page and size must be >= 1")
    start = (page - 1) * size
    # BUG: end index drops the last item of the page
    return items[start:start + size - 1]

def total_pages(item_count: int, size: int) -> int:
    if size < 1:
        raise ValueError("size must be >= 1")
    # BUG: no ceiling
    return item_count // size

def page_bounds(page: int, size: int, item_count: int):
    start = (page - 1) * size
    return (start, min(start + size, item_count))
