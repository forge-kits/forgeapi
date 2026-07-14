from __future__ import annotations

import inspect
from typing import Any, Callable

from .drivers.base import CacheDriver

_SENTINEL = object()


class _Cache:
    def __init__(self) -> None:
        self._driver: CacheDriver | None = None
        self._prefix: str = ""
        self._default_ttl: int | None = None

    def configure(
        self,
        driver: str = "memory",
        prefix: str = "",
        ttl: int | None = None,
        redis_url: str = "redis://localhost:6379/0",
    ) -> None:
        self._prefix = prefix
        self._default_ttl = ttl
        if driver == "redis":
            from .drivers.redis_ import RedisDriver
            self._driver = RedisDriver(url=redis_url)
        else:
            from .drivers.memory import MemoryDriver
            self._driver = MemoryDriver()

    @property
    def _backend(self) -> CacheDriver:
        if self._driver is None:
            from .drivers.memory import MemoryDriver
            self._driver = MemoryDriver()
        return self._driver

    def _k(self, key: str) -> str:
        return f"{self._prefix}{key}" if self._prefix else key

    async def get(self, key: str, default: Any = None) -> Any:
        value = await self._backend.get(self._k(key))
        return value if value is not None else default

    async def set(self, key: str, value: Any, ttl: int | None = _SENTINEL) -> None:  # type: ignore[assignment]
        actual_ttl = self._default_ttl if ttl is _SENTINEL else ttl
        await self._backend.set(self._k(key), value, actual_ttl)

    async def put(self, key: str, value: Any, ttl: int | None = _SENTINEL) -> None:  # type: ignore[assignment]
        await self.set(key, value, ttl)

    async def remember(self, key: str, fn: Callable, ttl: int | None = _SENTINEL) -> Any:  # type: ignore[assignment]
        value = await self.get(key)
        if value is None:
            value = await fn() if inspect.iscoroutinefunction(fn) else fn()
            await self.set(key, value, ttl)
        return value

    async def forget(self, key: str) -> bool:
        return await self._backend.forget(self._k(key))

    async def flush(self) -> None:
        await self._backend.flush()

    async def has(self, key: str) -> bool:
        return await self._backend.has(self._k(key))

    async def missing(self, key: str) -> bool:
        return not await self.has(key)

    async def pull(self, key: str, default: Any = None) -> Any:
        """Get and immediately delete."""
        value = await self.get(key, default)
        await self.forget(key)
        return value

    async def increment(self, key: str, amount: int = 1) -> int:
        return await self._backend.increment(self._k(key), amount)

    async def decrement(self, key: str, amount: int = 1) -> int:
        return await self._backend.decrement(self._k(key), amount)

    async def forever(self, key: str, value: Any) -> None:
        """Store with no expiry."""
        await self._backend.set(self._k(key), value, ttl=None)


Cache = _Cache()
