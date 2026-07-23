from abc import ABC, abstractmethod
from typing import Any, Awaitable, Callable


class BroadcastDriver(ABC):
    """Abstract base for broadcast transport drivers."""

    @abstractmethod
    async def connect(self) -> None: ...

    @abstractmethod
    async def disconnect(self) -> None: ...

    @abstractmethod
    async def emit(self, channel: str, data: Any) -> None: ...

    @abstractmethod
    async def listen_pubsub(self) -> None: ...

    @abstractmethod
    async def listen_stream(self, group: str, consumer: str) -> None: ...

    @abstractmethod
    def register(self, channel: str, handler: Callable[[dict], Awaitable[None]]) -> None: ...
