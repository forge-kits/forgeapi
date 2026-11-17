from __future__ import annotations

from forgeapi.queue.job import Job

from .message import MailMessage


class SendMailJob(Job):
    """Queue job that delivers one already rendered message."""

    def __init__(self, message: dict) -> None:
        self.message = message

    async def handle(self) -> None:
        from .mail import Mail

        await Mail.deliver(MailMessage.from_dict(self.message))
