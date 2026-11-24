def flatten_json(obj, prefix=""):
    out = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            key = f"{prefix}.{k}" if prefix else k
            if isinstance(v, (dict, list)):
                # BUG: fails to recurse for depth > 2 -> str() fallback
                inner = flatten_json(v, key)
                if inner:
                    out.update(inner)
                else:
                    out[key] = str(v)
            else:
                out[key] = v
    elif isinstance(obj, list):
        for i, v in enumerate(obj, start=1):
            # BUG: 1-based indices
            key = f"{prefix}.{i}" if prefix else str(i)
            if isinstance(v, (dict, list)):
                inner = flatten_json(v, key)
                if inner:
                    out.update(inner)
                else:
                    out[key] = str(v)
            else:
                out[key] = v
    return out

def unflatten(flat: dict) -> dict:
    result = {}
    for key, value in flat.items():
        parts = key.split(".")
        node = result
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = value
    return result
