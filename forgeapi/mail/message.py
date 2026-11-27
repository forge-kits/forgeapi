from __future__ import annotations

import base64
from dataclasses import dataclass, field
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid
from typing import Any, Iterable

from forgeapi.exceptions import ForgeAPIError


def as_list(value: str | Iterable[str] | None) -> list[str]:
    """Normalise ``"a@x.com"`` / ``["a@x.com", ...]`` / ``None`` to a list."""
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    return list(value)


@dataclass
class Attachment:
    filename: str
    content: bytes
    content_type: str = "application/octet-stream"


@dataclass
class MailMessage:
    """A fully rendered message — what a driver sends and what the queue stores."""

    subject: str
    to: list[str]
    from_address: str = ""
    from_name: str = ""
    cc: list[str] = field(default_factory=list)
    bcc: list[str] = field(default_factory=list)
    reply_to: str = ""
    text: str | None = None
    html: str | None = None
    attachments: list[Attachment] = field(default_factory=list)

    @property
    def recipients(self) -> list[str]:
        return [*self.to, *self.cc, *self.bcc]

    def validate(self) -> None:
        """Reject a message that cannot be sent, before it is sent or queued."""
        if not self.from_address:
            raise ForgeAPIError(
                "Mail has no sender address.",
                hint='Set "from_address" in the \"mail\" section of config/app.py or on the Mailable.',
            )
        if not self.recipients:
            raise ForgeAPIError("Mail has no recipients.", hint="Pass to= to Mail.send() / Mail.queue().")
        if self.text is None and self.html is None:
            raise ForgeAPIError(
                "Mail has no body.",
                hint="Set template / text_template (or html / text) on the Mailable.",
            )
        headers = [self.subject, self.from_address, self.from_name, self.reply_to, *self.recipients]
        headers += [a.filename for a in self.attachments]
        if any("\r" in h or "\n" in h for h in headers):
            raise ForgeAPIError("Mail headers must not contain line breaks.")

    def to_email(self) -> EmailMessage:
        """Build the MIME message.  Bcc recipients are not written to the headers."""
        msg = EmailMessage()
        msg["From"] = formataddr((self.from_name, self.from_address))
        msg["To"] = ", ".join(self.to)
        if self.cc:
            msg["Cc"] = ", ".join(self.cc)
        if self.reply_to:
            msg["Reply-To"] = self.reply_to
        msg["Subject"] = self.subject
        msg["Date"] = formatdate(localtime=True)
        msg["Message-ID"] = make_msgid(domain=self.from_address.rpartition("@")[2] or None)

        if self.text is not None:
            msg.set_content(self.text)
            if self.html is not None:
                msg.add_alternative(self.html, subtype="html")
        else:
            msg.set_content(self.html or "", subtype="html")

        for att in self.attachments:
            maintype, _, subtype = att.content_type.partition("/")
            msg.add_attachment(
                att.content,
                maintype=maintype or "application",
                subtype=subtype or "octet-stream",
                filename=att.filename,
            )
        return msg

    # ── queue payload ─────────────────────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        """JSON-safe form for the queue (attachment bytes are base64-encoded)."""
        return {
            "subject": self.subject,
            "to": self.to,
            "from_address": self.from_address,
            "from_name": self.from_name,
            "cc": self.cc,
            "bcc": self.bcc,
            "reply_to": self.reply_to,
            "text": self.text,
            "html": self.html,
            "attachments": [
                {
                    "filename": a.filename,
                    "content": base64.b64encode(a.content).decode("ascii"),
                    "content_type": a.content_type,
                }
                for a in self.attachments
            ],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MailMessage":
        attachments = [
            Attachment(a["filename"], base64.b64decode(a["content"]), a["content_type"])
            for a in data.get("attachments", [])
        ]
        return cls(**{**data, "attachments": attachments})
