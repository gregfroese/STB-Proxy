"""BFF configuration, read from the environment (systemd EnvironmentFile in prod)."""

from __future__ import annotations

import os
from pathlib import Path

_BFF_DIR = Path(__file__).resolve().parent
_DEFAULT_STATIC = _BFF_DIR.parent / "app" / "dist"


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() not in ("false", "0", "no", "off")


class Config:
    def __init__(self) -> None:
        self.proxy_url: str = os.environ.get("PROXY_URL", "http://192.168.5.71:8001").rstrip("/")
        self.public_origin: str = os.environ.get(
            "PUBLIC_ORIGIN", "https://watch.home.gregfroese.com"
        ).rstrip("/")
        self.session_secret: str = os.environ.get("SESSION_SECRET", "")
        self.fernet_key: str = os.environ.get("FERNET_KEY", "")
        self.fernet_fallback: str = os.environ.get("FERNET_KEYS_FALLBACK", "")

        self.lineup_ttl: int = _int("LINEUP_TTL", 30)
        self.epg_ttl: int = _int("EPG_TTL", 300)
        self.guide_ttl: int = _int("GUIDE_TTL", 300)
        self.idle: int = _int("IDLE", 3600)
        self.absolute_ttl: int = _int("ABS", 43200)
        self.revalidate: int = _int("REVALIDATE", 900)

        self.session_db: str = os.environ.get(
            "SESSION_DB", "/var/lib/stb-proxy-web/sessions.db"
        )
        static_dir = os.environ.get("STATIC_DIR", "")
        self.static_dir: Path = Path(static_dir) if static_dir else _DEFAULT_STATIC

        self.cookie_secure: bool = _bool("COOKIE_SECURE", True)
        self.request_timeout: int = _int("REQUEST_TIMEOUT", 15)
        self.stream_timeout: int = _int("STREAM_TIMEOUT", 30)

        # HLS fallback (ffmpeg remux) for streams mpegts.js can't play cleanly.
        self.hls_enabled: bool = _bool("HLS_ENABLED", True)
        self.hls_dir: str = os.environ.get("HLS_DIR", "/var/lib/stb-proxy-web/hls")
        self.hls_ttl: int = _int("HLS_TTL", 8)
        self.ffmpeg_bin: str = os.environ.get("FFMPEG_BIN", "ffmpeg")

    @property
    def cookie_name(self) -> str:
        # The __Host- prefix demands Secure + Path=/ + no Domain, so only in prod.
        return "__Host-session" if self.cookie_secure else "session"


config = Config()
