from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class CacheDriver(ABC):
    @abstractmethod
    async def get(self, key: str) -> Any: ...

    @abstractmethod
    async def set(self, key: str, value: Any, ttl: int | None = None) -> None: ...

    @abstractmethod
    async def forget(self, key: str) -> bool: ...

    @abstractmethod
    async def flush(self) -> None: ...

    @abstractmethod
    async def has(self, key: str) -> bool: ...

    @abstractmethod
    async def increment(self, key: str, amount: int = 1) -> int: ...

    @abstractmethod
    async def decrement(self, key: str, amount: int = 1) -> int: ...
