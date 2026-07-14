from __future__ import annotations

import json
from typing import Any

from .base import CacheDriver


class RedisDriver(CacheDriver):
    def __init__(self, url: str = "redis://localhost:6379/0") -> None:
        try:
            import redis.asyncio as aioredis
        except ImportError:
            raise ImportError("Redis driver requires redis. Install it: pip install forge-kits[redis]")
        self._client = aioredis.from_url(url, decode_responses=True)

    async def get(self, key: str) -> Any:
        raw = await self._client.get(key)
        if raw is None:
            return None
        return json.loads(raw)

    async def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        serialized = json.dumps(value, default=str)
        if ttl is not None:
            await self._client.setex(key, ttl, serialized)
        else:
            await self._client.set(key, serialized)

    async def forget(self, key: str) -> bool:
        return bool(await self._client.delete(key))

    async def flush(self) -> None:
        await self._client.flushdb()

    async def has(self, key: str) -> bool:
        return bool(await self._client.exists(key))

    async def increment(self, key: str, amount: int = 1) -> int:
        return int(await self._client.incrby(key, amount))

    async def decrement(self, key: str, amount: int = 1) -> int:
        return int(await self._client.decrby(key, amount))

    async def close(self) -> None:
        await self._client.aclose()
