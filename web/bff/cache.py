"""A tiny per-key TTL cache (spec 1.2 caching)."""

from __future__ import annotations

import threading
import time
from typing import Any


class TTLCache:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._data: dict[Any, tuple[Any, float]] = {}

    def get(self, key: Any) -> Any | None:
        with self._lock:
            entry = self._data.get(key)
            if entry is None:
                return None
            value, expires = entry
            if time.time() > expires:
                self._data.pop(key, None)
                return None
            return value

    def set(self, key: Any, value: Any, ttl: float) -> None:
        with self._lock:
            self._data[key] = (value, time.time() + ttl)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()
