"""
Lightweight in-process TTL cache. No Redis, no external service —
matches the pattern already established in health.py's connectivity
cache. Never silently serves expired data as fresh; the caller always
gets an explicit freshness label alongside the data.
"""

import time
from dataclasses import dataclass
from typing import Generic, Optional, TypeVar

from app.news_engine.models import CACHED, FRESH, STALE, UNAVAILABLE

T = TypeVar("T")


@dataclass
class CacheEntry(Generic[T]):
    value: T
    fetched_at: float


class TTLCache(Generic[T]):
    def __init__(self, ttl_seconds: float, stale_grace_seconds: float = 0):
        self._ttl = ttl_seconds
        self._grace = stale_grace_seconds
        self._store: dict[str, CacheEntry[T]] = {}

    def get(self, key: str):
        entry = self._store.get(key)
        if entry is None:
            return None, UNAVAILABLE

        age = time.monotonic() - entry.fetched_at
        if age <= self._ttl:
            return entry.value, FRESH if age < (self._ttl / 2) else CACHED
        if age <= self._ttl + self._grace:
            return entry.value, STALE

        return None, UNAVAILABLE

    def set(self, key: str, value: T) -> None:
        self._store[key] = CacheEntry(value=value, fetched_at=time.monotonic())

    def is_fresh(self, key: str) -> bool:
        _, freshness = self.get(key)
        return freshness in (FRESH, CACHED)
