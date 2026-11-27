import pytest

from forgeapi.config import KitConfig, load_config
from forgeapi.exceptions import ForgeAPIConfigError


@pytest.fixture
def config_dir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    d = tmp_path / "config"
    d.mkdir()
    return d


def write_app(config_dir, body: str) -> None:
    """``config/app.py`` with ``config = {body}``: the one file that holds every setting but the database."""
    (config_dir / "app.py").write_text("config = {" + body + "}\n")


class TestKitConfigDefaults:
    def test_default_project(self):
        cfg = KitConfig()
        assert cfg.project.name == "my-app"
        assert cfg.project.version == "0.1.0"
        assert cfg.project.debug is False

    def test_default_api_prefix(self):
        assert KitConfig().project.api_prefix == "/api/v1"

    def test_directory_layout_is_fixed(self):
        from forgeapi.config import layout

        assert layout.controllers_dir == "app/controllers"
        assert layout.models_dir == "database/models"
        assert not hasattr(KitConfig(), "structure")

    def test_default_http(self):
        cfg = KitConfig()
        assert cfg.http.cors is False
        assert cfg.http.rate_limit is False
        assert cfg.http.access_log is True

    def test_default_auth(self):
        cfg = KitConfig()
        assert cfg.auth.default == "api"
        assert cfg.auth.guards == {}

    def test_default_pagination(self):
        cfg = KitConfig()
        assert cfg.pagination.default_limit == 20
        assert cfg.pagination.max_limit == 100


class TestLoadConfig:
    def test_returns_defaults_when_no_dir(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        cfg = load_config()
        assert isinstance(cfg, KitConfig)
        assert cfg.project.name == "my-app"
        assert not cfg.provided("auth")

    def test_project_settings_are_top_level_keys(self, config_dir):
        write_app(config_dir, "'name': 'MyApp', 'version': '2.0.0', 'api_prefix': '/v2'")
        cfg = load_config()
        assert (cfg.project.name, cfg.project.version, cfg.project.api_prefix) == ("MyApp", "2.0.0", "/v2")

    def test_a_feature_is_a_key_of_its_own(self, config_dir):
        write_app(config_dir, "'http': {'cors': ['https://a.com'], 'rate_limit': 30, 'request_id': True}")
        cfg = load_config()
        assert cfg.http.cors == ["https://a.com"]
        assert cfg.http.rate_limit == 30
        assert cfg.http.request_id is True

    def test_partial_config_keeps_defaults(self, config_dir):
        write_app(config_dir, "'name': 'Partial'")
        cfg = load_config()
        assert cfg.project.name == "Partial"
        assert cfg.pagination.default_limit == 20

    def test_provided_tracks_the_keys_present(self, config_dir):
        write_app(config_dir, "'auth': {'guards': {'api': {'strategy': 'cookie'}}}")
        cfg = load_config()
        assert cfg.provided("auth")
        assert not cfg.provided("cache")
        assert not cfg.provided("queue")

    def test_a_commented_feature_is_off(self, config_dir):
        (config_dir / "app.py").write_text("config = {\n    'name': 'x',\n    # 'queue': {'queue': 'high'},\n}\n")
        assert not load_config().provided("queue")

    def test_custom_section_is_kept(self, config_dir):
        write_app(config_dir, "'services': {'stripe': {'key': 'k'}}")
        cfg = load_config()
        assert cfg.get("services.stripe.key") == "k"
        assert cfg.provided("services")

    def test_unknown_non_dict_key_is_a_typo_and_raises(self, config_dir):
        write_app(config_dir, "'debg': True")
        with pytest.raises(ForgeAPIConfigError, match='Unknown key "debg"') as exc:
            load_config()
        assert "debug" in exc.value.hint

    def test_old_section_files_are_rejected_with_migration_hint(self, config_dir):
        (config_dir / "auth.py").write_text("config = {}\n")
        (config_dir / "mail.py").write_text("config = {}\n")
        with pytest.raises(ForgeAPIConfigError, match="config/auth.py, config/mail.py are not read") as exc:
            load_config()
        assert "config/app.py" in exc.value.hint

    def test_underscore_files_are_ignored(self, config_dir):
        (config_dir / "__init__.py").write_text("")
        (config_dir / "_helpers.py").write_text("x = 1\n")
        write_app(config_dir, "'name': 'ok'")
        assert load_config().project.name == "ok"

    def test_app_file_without_config_dict_raises(self, config_dir):
        (config_dir / "app.py").write_text("x = 1\n")
        with pytest.raises(ForgeAPIConfigError, match="must define a module-level 'config' dict"):
            load_config()

    def test_database_section_from_bare_tortoise_orm(self, config_dir):
        (config_dir / "database.py").write_text("TORTOISE_ORM = {'connections': {}, 'apps': {}}\n")
        cfg = load_config()
        assert cfg.database.tortoise_orm == "config.database.TORTOISE_ORM"
        assert cfg.provided("database")

    def test_database_explicit_config_overrides_convention(self, config_dir):
        (config_dir / "database.py").write_text("TORTOISE_ORM = {}\nconfig = {'tortoise_orm': 'app.settings.ORM'}\n")
        assert load_config().database.tortoise_orm == "app.settings.ORM"

    def test_database_file_without_tortoise_orm_raises(self, config_dir):
        (config_dir / "database.py").write_text("x = 1\n")
        with pytest.raises(ForgeAPIConfigError, match="must define a TORTOISE_ORM"):
            load_config()

    def test_explicit_dir_path(self, tmp_path):
        d = tmp_path / "myconf"
        d.mkdir()
        (d / "app.py").write_text("config = {'name': 'explicit'}\n")
        assert load_config(str(d)).project.name == "explicit"

    def test_toml_path_raises(self, tmp_path):
        toml = tmp_path / "forgeapi.toml"
        toml.write_text('[project]\nname = "legacy"\n')
        with pytest.raises(ForgeAPIConfigError, match="no longer supported"):
            load_config(str(toml))


class TestBroadcastConfig:
    def test_defaults(self):
        from forgeapi.config import BroadcastConfig
        cfg = BroadcastConfig()
        assert cfg.driver == "redis"
        assert cfg.driver_options == {}

    def test_load_from_file(self, config_dir):
        write_app(config_dir, "'broadcast': {'driver_options': {'namespace': 'myapp', 'mode': 'stream'}}")
        cfg = load_config()
        assert cfg.broadcast.driver_options["namespace"] == "myapp"
        assert cfg.broadcast.driver_options["mode"] == "stream"
        assert cfg.provided("broadcast")

    def test_not_provided_without_the_key(self, config_dir):
        write_app(config_dir, "'name': 'x'")
        assert not load_config().provided("broadcast")


class TestSchedulerConfig:
    def test_defaults(self):
        from forgeapi.config import SchedulerConfig
        assert SchedulerConfig().schedule == "schedule.py"

    def test_load_from_file(self, config_dir):
        write_app(config_dir, "'scheduler': {'schedule': 'tasks/schedule.py'}")
        cfg = load_config()
        assert cfg.scheduler.schedule == "tasks/schedule.py"
        assert cfg.provided("scheduler")

    def test_not_provided_without_the_key(self, config_dir):
        write_app(config_dir, "'name': 'x'")
        assert not load_config().provided("scheduler")


class TestQueueConfig:
    def test_defaults(self):
        from forgeapi.config import QueueConfig
        assert QueueConfig().queue == "default"

    def test_load_from_file(self, config_dir):
        write_app(config_dir, "'queue': {'queue': 'high'}")
        cfg = load_config()
        assert cfg.queue.queue == "high"
        assert cfg.provided("queue")

    def test_not_provided_without_the_key(self, config_dir):
        write_app(config_dir, "'name': 'x'")
        assert not load_config().provided("queue")


class TestPaginationConfigValidation:
    def test_default_limit_must_be_positive(self):
        from pydantic import ValidationError as PydanticValidationError
        with pytest.raises(PydanticValidationError):
            from forgeapi.config import PaginationConfig
            PaginationConfig(default_limit=0, max_limit=100)

    def test_max_limit_must_be_positive(self):
        from pydantic import ValidationError as PydanticValidationError
        with pytest.raises(PydanticValidationError):
            from forgeapi.config import PaginationConfig
            PaginationConfig(default_limit=10, max_limit=0)

    def test_default_limit_exceeds_max_raises(self):
        from pydantic import ValidationError as PydanticValidationError
        with pytest.raises(PydanticValidationError, match="must not exceed"):
            from forgeapi.config import PaginationConfig
            PaginationConfig(default_limit=200, max_limit=100)

    def test_invalid_section_raises_forge_config_error(self, config_dir):
        write_app(config_dir, "'pagination': {'default_limit': -5}")
        with pytest.raises(ForgeAPIConfigError):
            load_config()

    def test_syntax_error_raises_forge_config_error(self, config_dir):
        (config_dir / "app.py").write_text("config = {unclosed\n")
        with pytest.raises(ForgeAPIConfigError, match="Error executing"):
            load_config()


class TestConfigFunction:
    """``config("services.stripe.key")``: a value by dotted path, without a Core object."""

    @pytest.fixture(autouse=True)
    def fresh_cache(self):
        from forgeapi.config import config

        config.clear()
        yield
        config.clear()

    def test_reads_a_custom_section_by_dotted_path(self, config_dir):
        from forgeapi.config import config

        write_app(config_dir, "'services': {'stripe': {'key': 'sk_1'}}")
        assert config("services.stripe.key") == "sk_1"

    def test_missing_key_gives_the_default(self, config_dir):
        from forgeapi.config import config

        write_app(config_dir, "'name': 'x'")
        assert config("services.stripe.key") is None
        assert config("services.stripe.key", "fallback") == "fallback"

    def test_project_settings_are_reached_by_their_plain_name(self, config_dir):
        from forgeapi.config import config

        write_app(config_dir, "'name': 'Shop', 'api_prefix': '/v2', 'auth': {'default': 'web'}")
        assert config("name") == "Shop"
        assert config("api_prefix") == "/v2"
        assert config("project.name") == "Shop"        # the section path works too
        assert config("auth.default") == "web"          # built-in sections are not affected

    def test_without_a_key_it_returns_the_whole_config(self, config_dir):
        from forgeapi.config import config

        write_app(config_dir, "'name': 'Shop'")
        assert isinstance(config(), KitConfig)

    def test_config_is_read_once_until_cleared(self, config_dir):
        from forgeapi.config import config

        write_app(config_dir, "'name': 'first'")
        assert config("name") == "first"
        write_app(config_dir, "'name': 'second'")
        assert config("name") == "first"      # kept
        config.clear()
        assert config("name") == "second"     # read again

    def test_core_hands_over_the_config_it_loaded(self, config_dir):
        from fastapi import FastAPI

        from forgeapi import Core, config_from_dict
        from forgeapi.config import config

        Core(FastAPI(), config=config_from_dict({"project": {"name": "from-core"}}))
        assert config("name") == "from-core"
