"""Server-side session store (spec 1.4).

Opaque token; only its sha256 is stored. The Account's ``user:pass`` is kept
Fernet-encrypted so the BFF can re-attach HTTP Basic upstream. Idle + absolute
expiry are enforced server-side.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken, MultiFernet

from .config import config

logger = logging.getLogger("stbweb.sessions")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    token_hash   TEXT PRIMARY KEY,
    created_at   REAL NOT NULL,
    last_seen_at REAL NOT NULL,
    username     TEXT NOT NULL,
    account      TEXT,
    basic_enc    BLOB NOT NULL,
    csrf         TEXT NOT NULL,
    user_agent   TEXT,
    remote_ip    TEXT
);
"""


def build_fernet() -> MultiFernet:
    """A Fernet (possibly MultiFernet) from FERNET_KEY + fallbacks.

    With no key configured (local dev), an ephemeral key is generated so the BFF
    still runs; sessions simply don't survive a restart.
    """
    keys: list[bytes] = []
    for raw in (config.fernet_key, config.fernet_fallback):
        for part in raw.split(","):
            part = part.strip()
            if part:
                keys.append(part.encode())
    if not keys:
        if config.session_secret:
            digest = hashlib.sha256(config.session_secret.encode()).digest()
            import base64

            keys.append(base64.urlsafe_b64encode(digest))
        else:
            logger.warning("FERNET_KEY not set; generating an ephemeral key (dev only)")
            keys.append(Fernet.generate_key())
    return MultiFernet([Fernet(k) for k in keys])


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@dataclass
class Session:
    token_hash: str
    username: str
    account: str | None
    basic_enc: bytes
    csrf: str
    created_at: float
    last_seen_at: float

    def basic(self, fernet: MultiFernet) -> tuple[str, str]:
        raw = fernet.decrypt(self.basic_enc).decode()
        user, _, password = raw.partition(":")
        return user, password


class SessionStore:
    def __init__(self, db_path: str, fernet: MultiFernet | None = None) -> None:
        self.db_path = db_path
        self.fernet = fernet or build_fernet()
        self._lock = threading.Lock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=5)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self) -> None:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(_SCHEMA)
        try:
            import os

            os.chmod(self.db_path, 0o600)
        except OSError:
            pass

    def create(
        self,
        username: str,
        account: str | None,
        password: str,
        user_agent: str | None,
        remote_ip: str | None,
    ) -> tuple[str, str]:
        token = secrets.token_urlsafe(32)
        csrf = secrets.token_urlsafe(24)
        now = time.time()
        basic_enc = self.fernet.encrypt(f"{username}:{password}".encode())
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO sessions (token_hash, created_at, last_seen_at, username, account,"
                " basic_enc, csrf, user_agent, remote_ip) VALUES (?,?,?,?,?,?,?,?,?)",
                (hash_token(token), now, now, username, account, basic_enc, csrf, user_agent, remote_ip),
            )
        return token, csrf

    def get(self, token: str) -> Session | None:
        if not token:
            return None
        now = time.time()
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM sessions WHERE token_hash = ?", (hash_token(token),)
            ).fetchone()
            if row is None:
                return None
            if self._expired(row, now):
                conn.execute("DELETE FROM sessions WHERE token_hash = ?", (row["token_hash"],))
                return None
            conn.execute(
                "UPDATE sessions SET last_seen_at = ? WHERE token_hash = ?",
                (now, row["token_hash"]),
            )
        return self._row_to_session(row)

    def peek(self, token: str) -> Session | None:
        """Like get() but does not slide the idle timer (used by the stream route)."""
        if not token:
            return None
        now = time.time()
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM sessions WHERE token_hash = ?", (hash_token(token),)
            ).fetchone()
            if row is None or self._expired(row, now):
                return None
        return self._row_to_session(row)

    def delete(self, token: str) -> None:
        with self._lock, self._connect() as conn:
            conn.execute("DELETE FROM sessions WHERE token_hash = ?", (hash_token(token),))

    def delete_hash(self, token_hash: str) -> None:
        with self._lock, self._connect() as conn:
            conn.execute("DELETE FROM sessions WHERE token_hash = ?", (token_hash,))

    def all_valid(self) -> list[Session]:
        now = time.time()
        with self._lock, self._connect() as conn:
            rows = conn.execute("SELECT * FROM sessions").fetchall()
        return [self._row_to_session(r) for r in rows if not self._expired(r, now)]

    def purge_expired(self) -> None:
        now = time.time()
        with self._lock, self._connect() as conn:
            rows = conn.execute("SELECT * FROM sessions").fetchall()
            for row in rows:
                if self._expired(row, now):
                    conn.execute(
                        "DELETE FROM sessions WHERE token_hash = ?", (row["token_hash"],)
                    )

    def _expired(self, row: sqlite3.Row, now: float) -> bool:
        return (
            now - row["last_seen_at"] > config.idle
            or now - row["created_at"] > config.absolute_ttl
        )

    @staticmethod
    def _row_to_session(row: sqlite3.Row) -> Session:
        return Session(
            token_hash=row["token_hash"],
            username=row["username"],
            account=row["account"],
            basic_enc=row["basic_enc"],
            csrf=row["csrf"],
            created_at=row["created_at"],
            last_seen_at=row["last_seen_at"],
        )
