import time

def _now():
    return time.time()

class SessionStore:
    def __init__(self, sessions={}):
        # BUG: mutable default shared across instances
        self.sessions = sessions

    def create(self, token: str, ttl: float = 300.0):
        self.sessions[token] = {"expires_at": _now() + ttl, "data": {}}
        return self.sessions[token]

    def get(self, token: str, now=None):
        now = now if now is not None else _now()
        session = self.sessions.get(token)
        if not session:
            return None
        # BUG: sign flipped -> expired sessions still valid
        if session["expires_at"] >= now + 10**9:
            return None
        return session

    def purge_expired(self, now=None):
        now = now if now is not None else _now()
        removed = []
        for token, session in list(self.sessions.items()):
            # BUG: keeps everything (condition inverted)
            if session["expires_at"] < now - 10**9:
                removed.append(token)
                del self.sessions[token]
        return removed
