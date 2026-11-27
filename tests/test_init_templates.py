"""`forgeapi init` database templates register every built-in model module."""
import pytest

from forgeapi.cli.commands.init_cmd import _CONFIG_DATABASE_TEMPLATES


@pytest.mark.parametrize("driver", sorted(_CONFIG_DATABASE_TEMPLATES))
def test_database_template_includes_cache_models(driver):
    source = _CONFIG_DATABASE_TEMPLATES[driver].format(name="demo")
    namespace: dict = {}
    exec(compile(source, f"config/database.py[{driver}]", "exec"), namespace)
    models = namespace["TORTOISE_ORM"]["apps"]["models"]["models"]
    assert "forgeapi.cache.models" in models
    assert "forgeapi.auth.models" in models
    assert "database.models" in models


def test_mail_template_is_valid_config():
    from forgeapi.cli.commands.init_cmd import _CONFIG_MAIL_TEMPLATE
    from forgeapi.config.models import MailConfig

    namespace: dict = {}
    exec(compile(_CONFIG_MAIL_TEMPLATE.format(name="demo"), "config/mail.py", "exec"), namespace)
    cfg = MailConfig(**namespace["config"])
    assert cfg.driver == "log" and cfg.from_address == "noreply@demo.local"


def test_cookie_auth_template_is_valid_and_needs_no_secret():
    from forgeapi.cli.commands.init_cmd import _CONFIG_AUTH_TEMPLATES, _ENV_VARS
    from forgeapi.auth.strategies.cookie import CookieStrategy

    namespace: dict = {}
    exec(compile(_CONFIG_AUTH_TEMPLATES["cookie"], "config/auth.py", "exec"), namespace)
    guard_cfg = dict(namespace["config"]["guards"]["web"])
    assert guard_cfg.pop("strategy") == "cookie" and guard_cfg.pop("model")
    assert isinstance(CookieStrategy.from_config(guard_cfg), CookieStrategy)
    assert "secret" not in guard_cfg and "COOKIE_SECRET" not in _ENV_VARS["cookie"]
