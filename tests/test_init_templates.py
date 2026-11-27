"""`forgeapi init` database templates register only the project models."""
import pytest

from forgeapi.cli.commands.init_cmd import _CONFIG_DATABASE_TEMPLATES


@pytest.mark.parametrize("driver", sorted(_CONFIG_DATABASE_TEMPLATES))
def test_database_template_lists_only_the_project_models(driver):
    source = _CONFIG_DATABASE_TEMPLATES[driver].format(name="demo")
    namespace: dict = {}
    exec(compile(source, f"config/database.py[{driver}]", "exec"), namespace)
    models = namespace["TORTOISE_ORM"]["apps"]["models"]["models"]
    # queue, scheduler, cache and permissions tables are opt-in: the project adds them when it needs them
    assert models == ["database.models"]


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
    assert guard_cfg["session_model"] == "database.models.session.Session"
    guard_cfg["session_model"] = "tests.fakes.FakeSession"   # the project module does not exist here
    assert isinstance(CookieStrategy.from_config(guard_cfg), CookieStrategy)
    assert "secret" not in guard_cfg and "COOKIE_SECRET" not in _ENV_VARS["cookie"]


def test_init_does_not_switch_on_features_that_need_their_own_tables():
    # a config file is what switches queue and scheduler on, so init leaves them out until the tables exist
    from forgeapi.cli.commands import init_cmd

    assert not hasattr(init_cmd, "_CONFIG_QUEUE_TEMPLATE")
    assert not hasattr(init_cmd, "_CONFIG_SCHEDULER_TEMPLATE")
    assert not hasattr(init_cmd, "_SCHEDULE_TEMPLATE")


@pytest.mark.parametrize("driver", sorted(_CONFIG_DATABASE_TEMPLATES))
def test_database_template_shows_the_opt_in_models_as_comments(driver):
    source = _CONFIG_DATABASE_TEMPLATES[driver].format(name="demo")
    for module in ("queue", "scheduling", "cache", "permissions"):
        assert f'# "forgeapi.{module}.models"' in source
