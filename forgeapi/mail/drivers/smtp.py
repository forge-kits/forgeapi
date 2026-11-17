from __future__ import annotations

from forgeapi.exceptions import ForgeAPIImportError
from forgeapi.logging import log

from ..message import MailMessage
from .base import MailDriver

_log = log.channel("mail.smtp")


class SmtpDriver(MailDriver):
    """Sends through an SMTP server (needs ``pip install forge-kits[mail]``).

    ``encryption``: ``"starttls"`` (port 587), ``"ssl"`` (port 465) or ``None``
    (plain, only for a local relay).
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 587,
        username: str = "",
        password: str = "",
        encryption: str | None = "starttls",
        timeout: float = 30,
    ) -> None:
        try:
            import aiosmtplib
        except ImportError as exc:
            raise ForgeAPIImportError(
                "The smtp mail driver requires aiosmtplib.",
                hint="pip install forge-kits[mail]",
            ) from exc
        self._smtp = aiosmtplib
        self._host = host
        self._port = port
        self._username = username or None
        self._password = password or None
        self._encryption = encryption
        self._timeout = timeout
        _log.debug("SmtpDriver ready: %s:%s encryption=%s", host, port, encryption)

    async def send(self, message: MailMessage) -> None:
        await self._smtp.send(
            message.to_email(),
            sender=message.from_address,
            recipients=message.recipients,
            hostname=self._host,
            port=self._port,
            username=self._username,
            password=self._password,
            start_tls=self._encryption == "starttls",
            use_tls=self._encryption == "ssl",
            timeout=self._timeout,
        )
        _log.debug("Mail sent: '%s' to %d recipient(s)", message.subject, len(message.recipients))
