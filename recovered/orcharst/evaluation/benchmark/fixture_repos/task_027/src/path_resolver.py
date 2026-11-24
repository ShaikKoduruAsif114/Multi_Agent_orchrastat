import os

def resolve_path(base: str, sub: str) -> str:
    # BUG: absolute 'sub' gets joined under base anyway
    if not sub:
        return base
    return os.path.join(base, sub)

def has_extension(name: str, ext: str) -> bool:
    # BUG: substring check matches anywhere in the name
    return ext in name

def is_within_root(root: str, target: str) -> bool:
    # BUG: naive prefix check, ignores '..' traversal
    normalized = os.path.normpath(target)
    return normalized.startswith(os.path.basename(root))
