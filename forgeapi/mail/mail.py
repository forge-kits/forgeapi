from __future__ import annotations

from typing import Any, Iterable

from forgeapi.exceptions import ForgeAPIConfigError

from .drivers.base import MailDriver
from .mailable import Mailable
from .message import MailMessage, as_list
from .templates import TemplateRenderer


class _Mail:
    def __init__(self) -> None:
        self._driver: MailDriver | None = None
        self._renderer: TemplateRenderer | None = None
        self._from_address: str = ""
        self._from_name: str = ""

    def configure(
        self,
        driver: str = "log",
        from_address: str = "",
        from_name: str = "",
        templates: str = "app/templates/mail",
        smtp: dict[str, Any] | None = None,
    ) -> None:
        self._from_address = from_address
        self._from_name = from_name
        self._renderer = TemplateRenderer(templates)
        if driver == "smtp":
            from .drivers.smtp import SmtpDriver
            self._driver = SmtpDriver(**(smtp or {}))
        elif driver == "log":
            from .drivers.log import LogDriver
            self._driver = LogDriver()
        else:
            raise ForgeAPIConfigError(
                f"Unknown mail driver '{driver}'.",
                hint='Valid values: "smtp", "log".',
            )

    def _ensure_configured(self) -> None:
        """Configure from the ``"mail"`` section of ``config/app.py`` when ``Core`` did not (e.g. a queue worker process)."""
        if self._driver is not None:
            return
        from forgeapi.config import load_config

        cfg = load_config()
        if not cfg.provided("mail"):
            raise ForgeAPIConfigError(
                "Mail is not configured.",
                hint='Add a \"mail\" section to config/app.py, e.g. "mail": {"driver": "log", "from_address": "noreply@example.com"}.',
            )
        m = cfg.mail
        self.configure(
            driver=m.driver,
            from_address=m.from_address,
            from_name=m.from_name,
            templates=m.templates,
            smtp=m.smtp.model_dump(),
        )

    def build(
        self,
        mailable: Mailable,
        *,
        to: str | Iterable[str] | None = None,
        cc: str | Iterable[str] | None = None,
        bcc: str | Iterable[str] | None = None,
    ) -> MailMessage:
        """Render *mailable* into a validated :class:`MailMessage`."""
        self._ensure_configured()
        assert self._renderer is not None
        context = mailable.context()
        text = mailable.text
        html = mailable.html
        if mailable.text_template:
            text = self._renderer.render(mailable.text_template, context)
        if mailable.template:
            html = self._renderer.render(mailable.template, context)

        message = MailMessage(
            subject=mailable.subject,
            to=as_list(to),
            cc=as_list(cc),
            bcc=as_list(bcc),
            from_address=mailable.from_address or self._from_address,
            from_name=self._from_name if mailable.from_name is None else mailable.from_name,
            reply_to=mailable.reply_to or "",
            text=text,
            html=html,
            attachments=mailable.attachments,
        )
        message.validate()
        return message

    async def send(self, mailable: Mailable, *, to=None, cc=None, bcc=None) -> None:
        """Render and send now.  Errors from the driver propagate to the caller."""
        await self.deliver(self.build(mailable, to=to, cc=cc, bcc=bcc))

    async def queue(
        self,
        mailable: Mailable,
        *,
        to=None,
        cc=None,
        bcc=None,
        delay: int = 0,
        queue: str | None = None,
    ) -> None:
        """Render now, send later from the queue worker (retried like any job).

        The message is rendered here, so the queue stores plain text/HTML
        (attachments included, base64-encoded) — not the Mailable object.
        """
        from forgeapi.queue import dispatch

        from .job import SendMailJob

        message = self.build(mailable, to=to, cc=cc, bcc=bcc)
        await dispatch(SendMailJob(message.to_dict()), delay=delay, queue=queue)

    async def deliver(self, message: MailMessage) -> None:
        """Hand an already rendered message to the driver."""
        self._ensure_configured()
        assert self._driver is not None
        message.validate()
        await self._driver.send(message)


Mail = _Mail()
