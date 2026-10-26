"""Small security helpers: login/sign-up rate limits and browser security headers."""
import os
import time
from collections import defaultdict, deque


class RateLimiter:
    """Allow at most `limit` events per `window` seconds for each key (kept in memory)."""

    def __init__(self, limit, window):
        self.limit, self.window = limit, window
        self.events = defaultdict(deque)

    def _prune(self, key):
        q, now = self.events[key], time.time()
        while q and now - q[0] > self.window:
            q.popleft()
        return q

    def retry_after(self, key):
        """Seconds until another attempt is allowed (0 if allowed now)."""
        q = self._prune(key)
        if len(q) < self.limit:
            return 0
        return max(1, int(self.window - (time.time() - q[0])))

    def add(self, key):
        self._prune(key).append(time.time())

    def reset(self, key):
        self.events.pop(key, None)


# 5 wrong passwords per email+address, and 30 per address, every 15 minutes
login_by_account = RateLimiter(5, 900)
login_by_address = RateLimiter(30, 900)
# 10 sign-ups per address per hour
signups_by_address = RateLimiter(10, 3600)


def minutes(seconds):
    return max(1, (seconds + 59) // 60)


def init_security(app):
    # The session cookie is only marked Secure when the site is served over https
    if os.environ.get("PUBLIC_BASE_URL", "").startswith("https://"):
        app.config["SESSION_COOKIE_SECURE"] = True

    @app.after_request
    def add_headers(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        # The camera is needed for the QR scanner; other sensors are not
        resp.headers.setdefault("Permissions-Policy", "camera=(self), microphone=(), geolocation=()")
        if resp.mimetype == "text/html":
            resp.headers.setdefault("Cache-Control", "no-store")  # no private pages in the back/forward cache
        return resp
