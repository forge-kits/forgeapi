from __future__ import annotations

import mimetypes
from pathlib import Path

from .message import Attachment


class Mailable:
    """One kind of e-mail: subject, templates and the data they need.

    Example::

        class Welcome(Mailable):
            subject = "Welcome!"
            template = "welcome.html"          # Jinja2, from the templates dir
            text_template = "welcome.txt"      # optional plain-text part

            def __init__(self, user):
                self.user = user               # public attributes go to the template

        await Mail.send(Welcome(user), to=user.email)

    Template context is the public instance attributes; override
    :meth:`context` to build it yourself.  Inline ``html`` / ``text`` strings
    are used as they are (not rendered as templates).
    """

    subject: str = ""
    template: str | None = None
    text_template: str | None = None
    html: str | None = None
    text: str | None = None
    #: Override the sender from the \"mail\" section of config/app.py for this mailable only.
    from_address: str | None = None
    from_name: str | None = None
    reply_to: str | None = None

    def context(self) -> dict:
        return {k: v for k, v in vars(self).items() if not k.startswith("_")}

    def attach(self, filename: str, content: bytes, content_type: str | None = None) -> "Mailable":
        """Attach in-memory *content*.  Returns ``self`` for chaining."""
        ctype = content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"
        self.__dict__.setdefault("_attachments", []).append(Attachment(filename, content, ctype))
        return self

    def attach_file(self, path: str | Path, filename: str | None = None) -> "Mailable":
        """Attach a file from disk."""
        p = Path(path)
        return self.attach(filename or p.name, p.read_bytes())

    @property
    def attachments(self) -> list[Attachment]:
        return list(self.__dict__.get("_attachments", []))
