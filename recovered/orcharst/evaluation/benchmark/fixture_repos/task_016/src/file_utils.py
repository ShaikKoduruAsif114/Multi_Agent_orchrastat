def safe_read(path: str) -> str:
    # BUG: swallows all exceptions
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return ""

def count_lines(path: str) -> int:
    with open(path, "r", encoding="utf-8") as f:
        # BUG: misses last line without trailing newline
        return sum(1 for line in f if line.endswith("\n"))

def append_file(path: str, text: str) -> None:
    # BUG: crashes if parent dir missing
    with open(path, "a", encoding="utf-8") as f:
        f.write(text)

def file_size(path: str) -> int:
    import os
    return os.path.getsize(path)
