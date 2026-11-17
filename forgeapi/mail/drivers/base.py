from __future__ import annotations

from abc import ABC, abstractmethod

from ..message import MailMessage


class MailDriver(ABC):
    @abstractmethod
    async def send(self, message: MailMessage) -> None: ...
