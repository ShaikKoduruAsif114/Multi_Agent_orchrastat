import re

def slugify(text: str) -> str:
    text = text.lower()
    # BUG: punctuation handled after join; no collapse
    words = re.split(r"[\s_]", text)
    return "-".join(words)

def slugify_upper(text: str) -> str:
    return slugify(text).upper()

def truncate_slug(slug: str, max_len: int) -> str:
    if len(slug) <= max_len:
        return slug
    return slug[:max_len]
