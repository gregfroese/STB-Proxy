"""Security hardening (spec 1.4 / ticket 11): headers, CSRF, login rate limiting."""

from __future__ import annotations

import hmac
import threading
import time
from urllib.parse import urlsplit

from fastapi import Request

from .config import config

CSP = (
    "default-src 'self'; "
    "script-src 'self'; "
    "worker-src 'self' blob:; "
    "child-src 'self' blob:; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: https:; "
    "media-src 'self' blob:; "
    "connect-src 'self'; "
    "font-src 'self' data:; "
    "object-src 'none'; "
    "base-uri 'self'; "
    "form-action 'self'; "
    "frame-ancestors 'none'"
)

SECURITY_HEADERS = {
    "Content-Security-Policy": CSP,
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
}


def apply_security_headers(headers: dict[str, str]) -> None:
    for key, value in SECURITY_HEADERS.items():
        headers[key] = value


def _origin_of(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}" if parts.scheme else ""


def check_origin(request: Request) -> bool:
    """CSRF defence for login: reject a cross-site Origin / Sec-Fetch-Site.

    Absent headers (non-browser clients) are allowed; a present Origin must match
    the configured public origin.
    """
    origin = request.headers.get("origin")
    if origin and _origin_of(origin) != _origin_of(config.public_origin):
        return False
    fetch_site = request.headers.get("sec-fetch-site")
    if fetch_site and fetch_site not in ("same-origin", "same-site", "none"):
        return False
    return True


def valid_csrf(session_csrf: str, header_value: str | None) -> bool:
    if not session_csrf or not header_value:
        return False
    return hmac.compare_digest(session_csrf, header_value)


class LoginLimiter:
    """Per-username exponential backoff (the BFF layer; Caddy limits per IP).

    Failures double the wait from ``base`` up to ``cap``; a success clears the
    record. Only the BFF sees the username, so this is where username-targeted
    guessing is slowed.
    """

    def __init__(self, base: float = 1.0, cap: float = 300.0, max_failures: int = 20) -> None:
        self.base = base
        self.cap = cap
        self.max_failures = max_failures
        self._lock = threading.Lock()
        self._state: dict[str, dict] = {}

    def retry_after(self, username: str) -> int:
        with self._lock:
            entry = self._state.get(username)
            if not entry:
                return 0
            remaining = entry["until"] - time.time()
            return max(0, int(remaining + 0.999))

    def record_failure(self, username: str) -> None:
        with self._lock:
            entry = self._state.setdefault(username, {"failures": 0, "until": 0.0})
            entry["failures"] += 1
            delay = min(self.cap, self.base * (2 ** min(entry["failures"] - 1, 20)))
            entry["until"] = time.time() + delay

    def record_success(self, username: str) -> None:
        with self._lock:
            self._state.pop(username, None)


login_limiter = LoginLimiter()
