class RateLimiter:
    def __init__(self, max_requests: int, window_sec: float):
        self.max_requests = max_requests
        self.window_sec = window_sec
        self._hits = []

    def allow_request(self, now: float) -> bool:
        # BUG: never prunes timestamps outside the window
        if len(self._hits) >= self.max_requests:
            return False
        self._hits.append(now)
        return True

    def hits_in_window(self, now: float) -> int:
        return len(self._hits)
