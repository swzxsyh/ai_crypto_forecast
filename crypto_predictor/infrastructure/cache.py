"""Cache interfaces and default in-memory cache."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Protocol


class CacheBackend(Protocol):
    def get(self, key: str) -> Any | None:
        ...

    def set(self, key: str, value: Any, ttl_seconds: float) -> None:
        ...

    def delete(self, key: str) -> None:
        ...


@dataclass
class CacheItem:
    value: Any
    expires_at: float


class MemoryCache:
    def __init__(self) -> None:
        self._items: dict[str, CacheItem] = {}

    def get(self, key: str) -> Any | None:
        item = self._items.get(key)
        if item is None:
            return None
        if item.expires_at < time.monotonic():
            self._items.pop(key, None)
            return None
        return item.value

    def set(self, key: str, value: Any, ttl_seconds: float) -> None:
        if ttl_seconds <= 0:
            return
        self._items[key] = CacheItem(value=value, expires_at=time.monotonic() + ttl_seconds)

    def delete(self, key: str) -> None:
        self._items.pop(key, None)


default_cache = MemoryCache()
