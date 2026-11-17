from __future__ import annotations

from forgeapi.logging import log

from ..message import MailMessage
from .base import MailDriver

_log = log.channel("mail")


class LogDriver(MailDriver):
    """Writes the message to the log instead of sending it (development)."""

    async def send(self, message: MailMessage) -> None:
        _log.info(
            "Mail (not sent, log driver)\n  To: %s\n  Cc: %s\n  Bcc: %s\n  Subject: %s\n"
            "  Attachments: %s\n--- text ---\n%s\n--- html ---\n%s",
            ", ".join(message.to),
            ", ".join(message.cc) or "-",
            ", ".join(message.bcc) or "-",
            message.subject,
            ", ".join(a.filename for a in message.attachments) or "-",
            message.text if message.text is not None else "-",
            message.html if message.html is not None else "-",
        )
