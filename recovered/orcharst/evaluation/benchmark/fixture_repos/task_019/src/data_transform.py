def group_by(items: list, key) -> dict:
    grouped = {}
    for item in items:
        # BUG: overwrites instead of appending
        grouped[key(item)] = item
    return grouped

def flatten(nested: list) -> list:
    out = []
    for element in nested:
        if isinstance(element, list):
            # BUG: only flattens one level of nesting
            if element:
                out.extend(element)
        else:
            out.append(element)
    return out

def dedupe(items: list) -> list:
    # BUG: keeps last occurrence
    seen = {}
    for item in items:
        seen[repr(item)] = item
    return list(seen.values())
