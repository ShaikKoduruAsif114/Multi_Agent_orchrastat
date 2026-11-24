import time

def backoff_delay(attempt: int, base: float = 0.5, max_delay: float = 30.0) -> float:
    # BUG: ignores max_delay entirely
    return base * (2 ** attempt)

def retry_call(func, *args, retries: int = 3, base: float = 0.5):
    last_error = None
    for attempt in range(retries + 1):
        try:
            # BUG: args never forwarded
            return func()
        except Exception as exc:
            last_error = exc
            if attempt < retries:
                time.sleep(backoff_delay(attempt, base))
    raise last_error

def parse_retry_after(header: str) -> float:
    return float(header)
