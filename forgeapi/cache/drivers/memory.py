from __future__ import annotations

import asyncio
import time
from typing import Any

from .base import CacheDriver


class MemoryDriver(CacheDriver):
    def __init__(self) -> None:
        self._store: dict[str, tuple[Any, float | None]] = {}
        self._lock = asyncio.Lock()

    def _expired(self, key: str) -> bool:
        if key not in self._store:
            return True
        _, expires_at = self._store[key]
        return expires_at is not None and time.monotonic() > expires_at

    async def get(self, key: str) -> Any:
        async with self._lock:
            if self._expired(key):
                self._store.pop(key, None)
                return None
            return self._store[key][0]

    async def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        expires_at = time.monotonic() + ttl if ttl is not None else None
        async with self._lock:
            self._store[key] = (value, expires_at)

    async def forget(self, key: str) -> bool:
        async with self._lock:
            return self._store.pop(key, None) is not None

    async def flush(self) -> None:
        async with self._lock:
            self._store.clear()

    async def has(self, key: str) -> bool:
        async with self._lock:
            if self._expired(key):
                self._store.pop(key, None)
                return False
            return key in self._store

    async def increment(self, key: str, amount: int = 1) -> int:
        async with self._lock:
            current = 0
            if key in self._store and not self._expired(key):
                current = int(self._store[key][0])
            _, expires_at = self._store.get(key, (None, None))
            self._store[key] = (current + amount, expires_at)
            return current + amount

    async def decrement(self, key: str, amount: int = 1) -> int:
        return await self.increment(key, -amount)
