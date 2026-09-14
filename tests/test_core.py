"""Tests for Core bootstrap: provider phases, zero-config, py-dict config."""

import pytest
from fastapi import FastAPI

from forgeapi import Core, Provider, env
from forgeapi.config import load_config


@pytest.fixture
def in_tmp_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return tmp_path


# ---------------------------------------------------------------------------
# Zero-config — the first thing every new user tries
# ---------------------------------------------------------------------------

class TestZeroConfig:
    def test_core_with_no_args_does_not_raise(self, in_tmp_cwd):
        core = Core(FastAPI())
        assert core.config.project.name == "my-app"

    def test_core_signature_is_app_only(self, in_tmp_cwd):
        with pytest.raises(TypeError):
            Core(FastAPI(), auth=True)


# ---------------------------------------------------------------------------
# Provider phases
# ---------------------------------------------------------------------------

class TestProviderPhases:
    def _write_providers_config(self, tmp_path, provider_names: str):
        (tmp_path / "config").mkdir(exist_ok=True)
        (tmp_path / "config" / "project.py").write_text(
            "import tests.test_core as tc\n"
            f"config = {{'providers': [{provider_names}]}}\n"
        )

    def test_all_register_before_any_boot(self, in_tmp_cwd):
        calls: list[str] = []

        class First(Provider):
            def register(self): calls.append("first.register")
            def boot(self): calls.append("first.boot")

        class Second(Provider):
            def register(self): calls.append("second.register")
            def boot(self): calls.append("second.boot")

        import tests.test_core as tc
        tc._first, tc._second = First, Second
        self._write_providers_config(in_tmp_cwd, "tc._first, tc._second")
        try:
            Core(FastAPI())
            assert calls.index("second.register") < calls.index("first.boot")
            assert calls == [
                "first.register", "second.register", "first.boot", "second.boot",
            ]
        finally:
            del tc._first, tc._second

    def test_providers_receive_app_and_config(self, in_tmp_cwd):
        seen = {}

        class Probe(Provider):
            def register(self):
                seen["app"] = self.app
                seen["config"] = self.config

        import tests.test_core as tc
        tc._probe = Probe
        self._write_providers_config(in_tmp_cwd, "tc._probe")
        try:
            app = FastAPI()
            core = Core(app)
            assert seen["app"] is app
            assert seen["config"] is core.config
        finally:
            del tc._probe


# ---------------------------------------------------------------------------
# Convention over configuration
# ---------------------------------------------------------------------------

class TestConventions:
    def test_no_auth_section_no_auth_provider(self, in_tmp_cwd):
        core = Core(FastAPI())
        names = [type(p).__name__ for p in core.providers]
        assert "AuthProvider" not in names
        assert core.auth is None

    def test_auth_section_enables_auth(self, in_tmp_cwd, isolated_auth):
        (in_tmp_cwd / "config").mkdir()
        (in_tmp_cwd / "config" / "auth.py").write_text(
            "config = {'guards': {'api': "
            "{'strategy': 'jwt', 'secret': 'conv_secret_key_for_tests!!!!!!'}}}\n"
        )
        core = Core(FastAPI())
        assert core.auth is not None
        assert core.auth.guard("api").name == "api"

    def test_empty_auth_guards_raise_helpful_error(self, in_tmp_cwd):
        from forgeapi.exceptions import ForgeAPIConfigError
        (in_tmp_cwd / "config").mkdir()
        (in_tmp_cwd / "config" / "auth.py").write_text("config = {}\n")
        with pytest.raises(ForgeAPIConfigError, match="no guards"):
            Core(FastAPI())

    def test_debug_from_config_adds_telescope(self, in_tmp_cwd):
        (in_tmp_cwd / "config").mkdir()
        (in_tmp_cwd / "config" / "project.py").write_text("config = {'debug': True}\n")
        core = Core(FastAPI())
        names = [type(p).__name__ for p in core.providers]
        assert "TelescopeProvider" in names

    def test_http_section_configures_middleware(self, in_tmp_cwd):
        (in_tmp_cwd / "config").mkdir()
        (in_tmp_cwd / "config" / "http.py").write_text(
            "config = {'cors': ['https://x.com'], 'rate_limit': 5, 'access_log': False}\n"
        )
        app = FastAPI()
        Core(app)
        mw_names = [m.cls.__name__ for m in app.user_middleware]
        assert "CORSMiddleware" in mw_names
        assert "RateLimitMiddleware" in mw_names
        assert "LoggingMiddleware" not in mw_names


# ---------------------------------------------------------------------------
# env() helper
# ---------------------------------------------------------------------------

class TestEnvHelper:
    def test_missing_returns_default(self, monkeypatch):
        monkeypatch.delenv("NOPE_XYZ", raising=False)
        assert env("NOPE_XYZ") is None
        assert env("NOPE_XYZ", "fallback") == "fallback"

    def test_bool_and_null_casting(self, monkeypatch):
        monkeypatch.setenv("FLAG_T", "true")
        monkeypatch.setenv("FLAG_F", "False")
        monkeypatch.setenv("FLAG_N", "null")
        monkeypatch.setenv("FLAG_S", "plain")
        assert env("FLAG_T") is True
        assert env("FLAG_F") is False
        assert env("FLAG_N") is None
        assert env("FLAG_S") == "plain"


# ---------------------------------------------------------------------------
# Custom sections + dot access
# ---------------------------------------------------------------------------

class TestCustomSections:
    def test_custom_section_via_dot_access(self, in_tmp_cwd):
        (in_tmp_cwd / "config").mkdir()
        (in_tmp_cwd / "config" / "services.py").write_text(
            "config = {'stripe': {'key': 'sk_test_123'}}\n"
        )
        cfg = load_config()
        assert cfg.get("services.stripe.key") == "sk_test_123"
        assert cfg.get("services.missing", "fallback") == "fallback"
        assert cfg.get("auth.default") == "api"


# ---------------------------------------------------------------------------
# Multi-guard auth from config
# ---------------------------------------------------------------------------

@pytest.fixture
def isolated_auth():
    """Snapshot and restore the global auth facade around a test."""
    from forgeapi.auth.facade import auth as global_auth
    saved_guards, saved_default = dict(global_auth._guards), global_auth._default
    global_auth._guards.clear()
    yield global_auth
    global_auth._guards.clear()
    global_auth._guards.update(saved_guards)
    global_auth._default = saved_default


class TestMultiGuardConfig:
    def test_guards_built_from_config(self, in_tmp_cwd, isolated_auth):
        (in_tmp_cwd / "config").mkdir()
        (in_tmp_cwd / "config" / "auth.py").write_text(
            "config = {\n"
            "    'default': 'api',\n"
            "    'guards': {\n"
            "        'api':   {'strategy': 'jwt', 'secret': 'api_secret_key_for_tests!!!!!'},\n"
            "        'admin': {'strategy': 'jwt', 'secret': 'admin_secret_key_for_tests!!!'},\n"
            "    },\n"
            "}\n"
        )
        Core(FastAPI())
        assert isolated_auth.guard("api").name == "api"
        assert isolated_auth.guard("admin").name == "admin"
        assert isolated_auth.guard().name == "api"  # default

        # guards are isolated — different secrets
        from forgeapi.auth.models import AuthUser
        from forgeapi.exceptions import TokenInvalidError
        user = AuthUser(id="1", auth_method="jwt")
        token = isolated_auth.token(user, guard="api")
        with pytest.raises(TokenInvalidError):
            isolated_auth.decode(token, guard="admin")
