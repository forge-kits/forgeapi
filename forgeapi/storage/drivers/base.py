from __future__ import annotations

from abc import ABC, abstractmethod


class StorageDriver(ABC):
    @abstractmethod
    async def put(self, path: str, data: bytes) -> str: ...

    @abstractmethod
    async def get(self, path: str) -> bytes: ...

    @abstractmethod
    async def delete(self, path: str) -> bool: ...

    @abstractmethod
    async def exists(self, path: str) -> bool: ...

    @abstractmethod
    async def list(self, directory: str = "") -> list[str]: ...

    @abstractmethod
    def url(self, path: str) -> str: ...
