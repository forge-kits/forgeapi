import pytest
from forgeapi.settings.base import BaseAppSettings


class TestBaseAppSettings:
    def test_defaults(self):
        settings = BaseAppSettings()
        assert settings.debug is False
        assert settings.app_name == "FastAPI App"

    def test_override_via_env(self, monkeypatch):
        monkeypatch.setenv("DEBUG", "true")
        monkeypatch.setenv("APP_NAME", "MyAPI")
        settings = BaseAppSettings()
        assert settings.debug is True
        assert settings.app_name == "MyAPI"

    def test_custom_subclass(self, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")

        class AppSettings(BaseAppSettings):
            database_url: str = ""

        settings = AppSettings()
        assert settings.database_url == "sqlite:///:memory:"

    def test_extra_env_vars_ignored(self, monkeypatch):
        monkeypatch.setenv("UNKNOWN_VAR_XYZ", "ignored")
        # Should not raise
        settings = BaseAppSettings()
        assert not hasattr(settings, "unknown_var_xyz")
