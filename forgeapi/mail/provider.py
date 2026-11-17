from forgeapi.foundation import Provider
from forgeapi.logging import log

_log = log.channel("mail.provider")


class MailProvider(Provider):
    """Configures the :class:`~forgeapi.mail.mail.Mail` facade.

    Boots when ``config/mail.py`` exists::

        config = {
            "driver": "log",                       # "log" | "smtp"
            "from_address": "noreply@example.com",
            "from_name": "My App",
            "templates": "app/templates/mail",
            "smtp": {"host": "smtp.example.com", "port": 587,
                     "username": "...", "password": "...", "encryption": "starttls"},
        }
    """

    def register(self) -> None:
        from . import Mail
        cfg = self.config.mail
        Mail.configure(
            driver=cfg.driver,
            from_address=cfg.from_address,
            from_name=cfg.from_name,
            templates=cfg.templates,
            smtp=cfg.smtp.model_dump(),
        )
        if cfg.driver == "log" and not self.config.project.debug:
            _log.warning("Mail driver is 'log': messages are written to the log and NOT sent.")
        _log.debug("Mail: driver=%s from=%s", cfg.driver, cfg.from_address)
