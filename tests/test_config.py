import pytest
from pathlib import Path

from forgeapi.config import KitConfig, load_config


class TestKitConfigDefaults:
    def test_default_project(self):
        cfg = KitConfig()
        assert cfg.project.name == "my-app"
        assert cfg.project.version == "0.1.0"

    def test_default_structure(self):
        cfg = KitConfig()
        assert cfg.structure.base_prefix == "/api/v1"
        assert cfg.structure.controllers_dir == "app/controllers"

    def test_default_auth(self):
        cfg = KitConfig()
        assert cfg.auth.strategy == "jwt"
        assert cfg.auth.access_ttl_minutes == 30
        assert cfg.auth.refresh_ttl_days == 7

    def test_default_pagination(self):
        cfg = KitConfig()
        assert cfg.pagination.default_limit == 20
        assert cfg.pagination.max_limit == 100


class TestLoadConfig:
    def test_returns_defaults_when_no_file(self, tmp_path):
        cfg = load_config(str(tmp_path / "nonexistent.toml"))
        assert isinstance(cfg, KitConfig)
        assert cfg.project.name == "my-app"

    def test_reads_project_section(self, tmp_path):
        toml = tmp_path / "forgeapi.toml"
        toml.write_text(
            '[project]\nname = "MyApp"\nversion = "2.0.0"\n',
            encoding="utf-8",
        )
        cfg = load_config(str(toml))
        assert cfg.project.name == "MyApp"
        assert cfg.project.version == "2.0.0"

    def test_reads_pagination_section(self, tmp_path):
        toml = tmp_path / "forgeapi.toml"
        toml.write_text(
            "[pagination]\ndefault_limit = 10\nmax_limit = 50\n",
            encoding="utf-8",
        )
        cfg = load_config(str(toml))
        assert cfg.pagination.default_limit == 10
        assert cfg.pagination.max_limit == 50

    def test_reads_structure_section(self, tmp_path):
        toml = tmp_path / "forgeapi.toml"
        toml.write_text(
            '[structure]\nbase_prefix = "/v2"\ncontrollers_dir = "controllers"\n',
            encoding="utf-8",
        )
        cfg = load_config(str(toml))
        assert cfg.structure.base_prefix == "/v2"
        assert cfg.structure.controllers_dir == "controllers"

    def test_partial_toml_keeps_defaults(self, tmp_path):
        toml = tmp_path / "forgeapi.toml"
        toml.write_text('[project]\nname = "Partial"\n', encoding="utf-8")
        cfg = load_config(str(toml))
        assert cfg.project.name == "Partial"
        assert cfg.pagination.default_limit == 20


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

    def test_invalid_toml_raises_forge_config_error(self, tmp_path):
        from forgeapi.exceptions import ForgeAPIConfigError
        toml = tmp_path / "forgeapi.toml"
        toml.write_text("[pagination]\ndefault_limit = -5\n", encoding="utf-8")
        with pytest.raises(ForgeAPIConfigError):
            load_config(str(toml))

    def test_toml_syntax_error_raises(self, tmp_path):
        import tomllib
        toml = tmp_path / "forgeapi.toml"
        toml.write_text("name = [unclosed\n", encoding="utf-8")
        with pytest.raises(tomllib.TOMLDecodeError):
            load_config(str(toml))
