"""Mail: Mailable rendering, message building, drivers, queueing."""
import logging
import sys
import types

import pytest
from pydantic import ValidationError
from tortoise import Tortoise
import tortoise.timezone as tt

from forgeapi.config.models import KitConfig, MailConfig
from forgeapi.exceptions import ForgeAPIConfigError, ForgeAPIError, ForgeAPIImportError
from forgeapi.mail import Mail, Mailable, MailMessage, SendMailJob
from forgeapi.mail.drivers.base import MailDriver
from forgeapi.mail.mail import _Mail
from forgeapi.queue import Queue


class Recorder(MailDriver):
    def __init__(self):
        self.sent: list[MailMessage] = []

    async def send(self, message):
        self.sent.append(message)


class Welcome(Mailable):
    subject = "Welcome"
    template = "welcome.html"
    text_template = "welcome.txt"

    def __init__(self, name):
        self.name = name


@pytest.fixture
def templates(tmp_path):
    (tmp_path / "welcome.html").write_text("<p>Hi {{ name }}</p>")
    (tmp_path / "welcome.txt").write_text("Hi {{ name }}")
    return tmp_path


@pytest.fixture
def mail(templates):
    m = _Mail()
    m.configure(driver="log", from_address="noreply@app.test", from_name="App", templates=str(templates))
    m._driver = Recorder()
    return m


# ── rendering / building ──────────────────────────────────────────────────────

def test_build_renders_both_parts(mail):
    msg = mail.build(Welcome("Ana"), to="a@x.com")
    assert msg.html == "<p>Hi Ana</p>"
    assert msg.text == "Hi Ana"
    assert (msg.from_address, msg.from_name, msg.to) == ("noreply@app.test", "App", ["a@x.com"])


def test_html_is_escaped_text_is_not(mail):
    msg = mail.build(Welcome("<b>x</b>"), to="a@x.com")
    assert msg.html == "<p>Hi &lt;b&gt;x&lt;/b&gt;</p>"
    assert msg.text == "Hi <b>x</b>"


def test_missing_variable_raises(mail):
    class Broken(Mailable):
        subject = "s"
        template = "welcome.html"   # needs `name`, which is never set

    with pytest.raises(Exception) as exc:
        mail.build(Broken(), to="a@x.com")
    assert "name" in str(exc.value)


def test_missing_template_gives_hint(mail):
    class Ghost(Mailable):
        subject = "s"
        template = "nope.html"

    with pytest.raises(ForgeAPIConfigError) as exc:
        mail.build(Ghost(), to="a@x.com")
    assert "nope.html" in str(exc.value)


def test_mailable_overrides_sender(mail):
    class Custom(Welcome):
        from_address = "billing@app.test"
        from_name = ""
        reply_to = "help@app.test"

    msg = mail.build(Custom("Ana"), to="a@x.com")
    assert (msg.from_address, msg.from_name, msg.reply_to) == ("billing@app.test", "", "help@app.test")


def test_inline_text_body(mail):
    class Plain(Mailable):
        subject = "s"
        text = "just text"

    assert mail.build(Plain(), to="a@x.com").text == "just text"


@pytest.mark.parametrize("kwargs,needle", [
    ({}, "recipients"),
    ({"to": "a@x.com\nBcc: evil@x.com"}, "line breaks"),
])
def test_validation_errors(mail, kwargs, needle):
    with pytest.raises(ForgeAPIError) as exc:
        mail.build(Welcome("Ana"), **kwargs)
    assert needle in str(exc.value)


def test_no_body_and_no_sender_rejected(templates):
    class Empty(Mailable):
        subject = "s"

    m = _Mail()
    m.configure(driver="log", from_address="a@app.test", templates=str(templates))
    with pytest.raises(ForgeAPIError, match="no body"):
        m.build(Empty(), to="a@x.com")

    m2 = _Mail()
    m2.configure(driver="log", templates=str(templates))
    with pytest.raises(ForgeAPIError, match="sender"):
        m2.build(Welcome("Ana"), to="a@x.com")


# ── MIME ──────────────────────────────────────────────────────────────────────

def test_to_email_multipart_attachment_and_bcc(mail):
    mailable = Welcome("Ana").attach("r.txt", b"data", "text/plain")
    msg = mail.build(mailable, to=["a@x.com", "b@x.com"], cc="c@x.com", bcc="hidden@x.com")
    email = msg.to_email()
    assert email["To"] == "a@x.com, b@x.com"
    assert email["Cc"] == "c@x.com"
    assert email["Bcc"] is None
    assert email["From"] == "App <noreply@app.test>"
    assert email["Message-ID"] and email["Date"]
    kinds = [p.get_content_type() for p in email.walk()]
    assert "text/plain" in kinds and "text/html" in kinds
    assert [p.get_filename() for p in email.iter_attachments()] == ["r.txt"]
    assert msg.recipients == ["a@x.com", "b@x.com", "c@x.com", "hidden@x.com"]


def test_html_only_message(mail):
    class HtmlOnly(Mailable):
        subject = "s"
        template = "welcome.html"

        def __init__(self):
            self.name = "Ana"

    email = mail.build(HtmlOnly(), to="a@x.com").to_email()
    assert email.get_content_type() == "text/html"


def test_attach_file(tmp_path):
    f = tmp_path / "doc.pdf"
    f.write_bytes(b"%PDF")
    att = Mailable().attach_file(f).attachments[0]
    assert (att.filename, att.content, att.content_type) == ("doc.pdf", b"%PDF", "application/pdf")


def test_dict_roundtrip_keeps_attachments(mail):
    msg = mail.build(Welcome("Ana").attach("a.bin", b"\x00\xff"), to="a@x.com", cc="c@x.com")
    back = MailMessage.from_dict(msg.to_dict())
    assert back == msg


# ── sending ───────────────────────────────────────────────────────────────────

async def test_send_hands_message_to_driver(mail):
    await mail.send(Welcome("Ana"), to="a@x.com")
    assert [m.subject for m in mail._driver.sent] == ["Welcome"]


async def test_log_driver_writes_log_and_sends_nothing(templates, caplog):
    m = _Mail()
    m.configure(driver="log", from_address="n@app.test", templates=str(templates))
    with caplog.at_level(logging.INFO, logger="forgeapi.mail"):
        await m.send(Welcome("Ana"), to="a@x.com")
    assert "not sent" in caplog.text and "Hi Ana" in caplog.text


def test_unknown_driver_raises():
    with pytest.raises(ForgeAPIConfigError):
        _Mail().configure(driver="carrier-pigeon")


def test_unconfigured_mail_raises(monkeypatch):
    monkeypatch.setattr("forgeapi.config.load_config", lambda *a, **k: KitConfig())
    with pytest.raises(ForgeAPIConfigError, match="not configured"):
        _Mail()._ensure_configured()


def test_lazy_configure_from_project_config(monkeypatch, templates):
    cfg = KitConfig(mail={"driver": "log", "from_address": "n@app.test", "templates": str(templates)})
    cfg._provided = {"mail"}
    monkeypatch.setattr("forgeapi.config.load_config", lambda *a, **k: cfg)
    m = _Mail()
    assert m.build(Welcome("Ana"), to="a@x.com").from_address == "n@app.test"


# ── smtp driver ───────────────────────────────────────────────────────────────

def _install_fake_smtp(monkeypatch):
    calls = []

    async def send(message, **kwargs):
        calls.append((message, kwargs))

    monkeypatch.setitem(sys.modules, "aiosmtplib", types.SimpleNamespace(send=send))
    return calls


@pytest.mark.parametrize("encryption,start_tls,use_tls", [
    ("starttls", True, False),
    ("ssl", False, True),
    (None, False, False),
])
async def test_smtp_driver_arguments(monkeypatch, mail, encryption, start_tls, use_tls):
    calls = _install_fake_smtp(monkeypatch)
    from forgeapi.mail.drivers.smtp import SmtpDriver

    driver = SmtpDriver(host="smtp.test", port=2525, username="u", password="p", encryption=encryption)
    await driver.send(mail.build(Welcome("Ana"), to="a@x.com", bcc="h@x.com"))

    message, kw = calls[0]
    assert message["Subject"] == "Welcome"
    assert kw["sender"] == "noreply@app.test"
    assert kw["recipients"] == ["a@x.com", "h@x.com"]   # bcc is delivered, not in headers
    assert (kw["hostname"], kw["port"], kw["username"], kw["password"]) == ("smtp.test", 2525, "u", "p")
    assert (kw["start_tls"], kw["use_tls"]) == (start_tls, use_tls)


def test_smtp_driver_without_library(monkeypatch):
    monkeypatch.setitem(sys.modules, "aiosmtplib", None)
    from forgeapi.mail.drivers.smtp import SmtpDriver

    with pytest.raises(ForgeAPIImportError, match="forge-kits\\[mail\\]"):
        SmtpDriver()


def test_mail_config_validates_encryption():
    assert MailConfig().driver == "log"
    with pytest.raises(ValidationError):
        MailConfig(smtp={"encryption": "tls1.0"})


# ── queue ─────────────────────────────────────────────────────────────────────

async def test_queue_renders_now_and_worker_sends_later(templates, monkeypatch):
    # dispatch() uses the global queue: pin its timezone to the worker's
    monkeypatch.setattr("forgeapi.support.clock.config_timezone", lambda: "UTC")
    monkeypatch.setattr("forgeapi.queue.queue._queue._tz_resolved", False)
    monkeypatch.setattr("forgeapi.queue.queue._queue._timezone", None)
    await Tortoise.init(
        db_url="sqlite://:memory:",
        modules={"models": ["forgeapi.queue.models"]},
    )
    await Tortoise.generate_schemas()
    recorder = Recorder()
    saved = (Mail._driver, Mail._renderer, Mail._from_address, Mail._from_name)
    try:
        Mail.configure(driver="log", from_address="n@app.test", templates=str(templates))
        Mail._driver = recorder

        await Mail.queue(Welcome("Ana").attach("a.txt", b"x"), to="a@x.com")
        assert recorder.sent == []                      # nothing sent yet

        from forgeapi.queue.models import JobRecord
        record = await JobRecord.first()
        assert record.payload["class"] == "forgeapi.mail.job.SendMailJob"
        assert record.payload["data"]["message"]["html"] == "<p>Hi Ana</p>"

        assert await Queue(timezone="UTC").run_next() is True
        assert len(recorder.sent) == 1
        assert recorder.sent[0].attachments[0].content == b"x"
    finally:
        Mail._driver, Mail._renderer, Mail._from_address, Mail._from_name = saved
        await Tortoise.close_connections()
        tt._reset_timezone_cache()


async def test_queue_rejects_invalid_message_before_dispatch(mail):
    with pytest.raises(ForgeAPIError, match="recipients"):
        await mail.queue(Welcome("Ana"))
