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


def _app_config(strategy: str, name: str = "demo") -> dict:
    from forgeapi.cli.commands.init_cmd import _config_app

    namespace: dict = {}
    exec(compile(_config_app(name, strategy), "config/app.py", "exec"), namespace)
    return namespace["config"]


@pytest.mark.parametrize("strategy", ["cookie", "telegram"])
def test_app_template_loads_as_a_valid_config(strategy, tmp_path, monkeypatch):
    # arrange: write the generated config/app.py, act: load it the way Core does, assert: the sections are there
    from forgeapi.cli.commands.init_cmd import _config_app
    from forgeapi.config import load_config

    monkeypatch.setenv("BOT_TOKEN", "123:abc")
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "app.py").write_text(_config_app("demo", strategy))

    cfg = load_config(str(tmp_path / "config"))

    assert cfg.project.name == "demo" and cfg.project.api_prefix == "/api/v1"
    assert cfg.mail.driver == "log" and cfg.mail.from_address == "noreply@demo.local"
    assert {"auth", "http", "pagination", "storage", "cache", "mail", "broadcast"} <= cfg._provided
    # opt-in features are commented out until their tables exist
    assert not cfg.provided("queue") and not cfg.provided("scheduler")


def test_cookie_auth_block_is_valid_and_needs_no_secret():
    from forgeapi.cli.commands.init_cmd import _ENV_VARS
    from forgeapi.auth.strategies.cookie import CookieStrategy

    guard_cfg = dict(_app_config("cookie")["auth"]["guards"]["web"])
    assert guard_cfg.pop("strategy") == "cookie" and guard_cfg.pop("model")
    assert guard_cfg["session_model"] == "database.models.session.Session"
    guard_cfg["session_model"] = "tests.fakes.FakeSession"   # the project module does not exist here
    assert isinstance(CookieStrategy.from_config(guard_cfg), CookieStrategy)
    assert "secret" not in guard_cfg and "COOKIE_SECRET" not in _ENV_VARS["cookie"]


def test_init_does_not_switch_on_features_that_need_their_own_tables():
    # a feature is on while its key is in config/app.py, so queue and scheduler stay commented out
    from forgeapi.cli.commands.init_cmd import _config_app

    source = _config_app("demo", "cookie")
    assert '# "queue": {' in source and '# "scheduler": {' in source


@pytest.mark.parametrize("driver", sorted(_CONFIG_DATABASE_TEMPLATES))
def test_database_template_shows_the_opt_in_models_as_comments(driver):
    source = _CONFIG_DATABASE_TEMPLATES[driver].format(name="demo")
    for module in ("queue", "scheduling", "cache", "permissions"):
        assert f'# "forgeapi.{module}.models"' in source


@pytest.mark.parametrize("strategy", ["cookie", "telegram"])
def test_every_key_of_the_app_template_is_known_to_its_config_model(strategy):
    # a key the model does not know is ignored without a word, e.g. "allow_credentials" vs "cors_allow_credentials"
    from forgeapi.config.models import KitConfig, ProjectConfig

    config = _app_config(strategy)
    sections = {name: value for name, value in config.items() if isinstance(value, dict)}
    project = {name for name, value in config.items() if not isinstance(value, dict)}
    assert project <= set(ProjectConfig.model_fields)
    for name, values in sections.items():
        model = KitConfig.model_fields[name].annotation
        assert set(values) <= set(model.model_fields), (name, set(values) - set(model.model_fields))
