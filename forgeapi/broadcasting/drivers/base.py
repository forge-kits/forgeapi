from abc import ABC, abstractmethod
from typing import Awaitable, Callable


class BroadcastDriver(ABC):

    @abstractmethod
    async def connect(self) -> None: ...

    @abstractmethod
    async def disconnect(self) -> None: ...

    @abstractmethod
    async def emit(self, channel: str, payload: dict) -> None: ...

    @abstractmethod
    async def listen(self) -> None: ...

    @abstractmethod
    def register(self, channel: str, handler: Callable[[dict], Awaitable[None]]) -> None: ...

    @abstractmethod
    async def wait_bg_tasks(self) -> None: ...

    @property
    def has_listeners(self) -> bool:
        return False
