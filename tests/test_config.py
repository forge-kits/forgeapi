import pytest

from forgeapi.config import KitConfig, load_config


@pytest.fixture
def config_dir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    d = tmp_path / "config"
    d.mkdir()
    return d


class TestKitConfigDefaults:
    def test_default_project(self):
        cfg = KitConfig()
        assert cfg.project.name == "my-app"
        assert cfg.project.version == "0.1.0"
        assert cfg.project.debug is False

    def test_default_structure(self):
        cfg = KitConfig()
        assert cfg.structure.base_prefix == "/api/v1"
        assert cfg.structure.controllers_dir == "app/controllers"

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

    def test_reads_project_section(self, config_dir):
        (config_dir / "project.py").write_text(
            "config = {'name': 'MyApp', 'version': '2.0.0'}\n"
        )
        cfg = load_config()
        assert cfg.project.name == "MyApp"
        assert cfg.project.version == "2.0.0"

    def test_reads_http_section(self, config_dir):
        (config_dir / "http.py").write_text(
            "config = {'cors': ['https://a.com'], 'rate_limit': 30, 'request_id': True}\n"
        )
        cfg = load_config()
        assert cfg.http.cors == ["https://a.com"]
        assert cfg.http.rate_limit == 30
        assert cfg.http.request_id is True

    def test_partial_config_keeps_defaults(self, config_dir):
        (config_dir / "project.py").write_text("config = {'name': 'Partial'}\n")
        cfg = load_config()
        assert cfg.project.name == "Partial"
        assert cfg.pagination.default_limit == 20

    def test_provided_tracks_user_sections(self, config_dir):
        (config_dir / "auth.py").write_text(
            "config = {'guards': {'api': {'strategy': 'jwt', 'secret': 'x' * 32}}}\n"
        )
        cfg = load_config()
        assert cfg.provided("auth")
        assert not cfg.provided("cache")

    def test_database_section_from_bare_tortoise_orm(self, config_dir):
        (config_dir / "database.py").write_text(
            "TORTOISE_ORM = {'connections': {}, 'apps': {}}\n"
        )
        cfg = load_config()
        assert cfg.database.tortoise_orm == "config.database.TORTOISE_ORM"
        assert cfg.provided("database")

    def test_database_explicit_config_overrides_convention(self, config_dir):
        (config_dir / "database.py").write_text(
            "TORTOISE_ORM = {}\nconfig = {'tortoise_orm': 'app.settings.ORM'}\n"
        )
        cfg = load_config()
        assert cfg.database.tortoise_orm == "app.settings.ORM"

    def test_non_database_file_without_config_raises(self, config_dir):
        from forgeapi.exceptions import ForgeAPIConfigError
        (config_dir / "cache.py").write_text("TORTOISE_ORM = {}\n")
        with pytest.raises(ForgeAPIConfigError, match="must define"):
            load_config()

    def test_explicit_dir_path(self, tmp_path):
        d = tmp_path / "myconf"
        d.mkdir()
        (d / "project.py").write_text("config = {'name': 'explicit'}\n")
        cfg = load_config(str(d))
        assert cfg.project.name == "explicit"

    def test_toml_path_raises(self, tmp_path):
        from forgeapi.exceptions import ForgeAPIConfigError
        toml = tmp_path / "forgeapi.toml"
        toml.write_text('[project]\nname = "legacy"\n')
        with pytest.raises(ForgeAPIConfigError, match="no longer supported"):
            load_config(str(toml))


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
        from forgeapi.exceptions import ForgeAPIConfigError
        (config_dir / "pagination.py").write_text("config = {'default_limit': -5}\n")
        with pytest.raises(ForgeAPIConfigError):
            load_config()

    def test_syntax_error_raises_forge_config_error(self, config_dir):
        from forgeapi.exceptions import ForgeAPIConfigError
        (config_dir / "cache.py").write_text("config = {unclosed\n")
        with pytest.raises(ForgeAPIConfigError, match="Error executing"):
            load_config()
