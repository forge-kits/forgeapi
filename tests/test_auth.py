"""Tests for auth: Guard, Auth facade, strategy factories (sessions: test_auth_session.py)."""
import pytest
from starlette.requests import Request as StarletteRequest
from starlette.responses import Response as StarletteResponse

from forgeapi.auth.strategies.cookie import CookieStrategy
from forgeapi.auth.guard import Guard
from forgeapi.auth.facade import Auth
from types import SimpleNamespace
from forgeapi.exceptions import ForgeAPIConfigError
from tests.fakes import FakeSession, FakeUser


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_request(headers: dict | None = None, cookies: dict | None = None) -> StarletteRequest:
    raw_headers = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    cookie_header = "; ".join(f"{k}={v}" for k, v in (cookies or {}).items())
    if cookie_header:
        raw_headers.append((b"cookie", cookie_header.encode()))
    return StarletteRequest({
        "type": "http", "method": "GET", "path": "/",
        "headers": raw_headers, "query_string": b"",
    })


def make_response() -> StarletteResponse:
    return StarletteResponse()


def fresh_auth() -> Auth:
    return Auth()


# ---------------------------------------------------------------------------
# CookieStrategy — construction
# ---------------------------------------------------------------------------

class TestCookieStrategyConstruction:
    def test_defaults(self):
        s = CookieStrategy(FakeSession)
        assert s._cookie_name == "session"
        assert s._lifetime == 3600
        assert s._absolute_lifetime is None
        assert s._secure is True

    def test_from_config_reads_keys(self):
        s = CookieStrategy.from_config({
            "session_model": "tests.fakes.FakeSession",
            "cookie_name": "auth", "lifetime": 60, "absolute_lifetime": 600,
            "secure": False, "samesite": "strict",
        })
        assert (s._cookie_name, s._lifetime, s._absolute_lifetime) == ("auth", 60, 600)
        assert s._secure is False and s._samesite == "strict"

    def test_from_config_ignores_the_old_secret_key(self):
        cfg = {"secret": "left over from a signed-cookie config", "session_model": "tests.fakes.FakeSession"}
        assert CookieStrategy.from_config(cfg)._cookie_name == "session"

    def test_from_config_needs_the_session_model(self):
        with pytest.raises(ForgeAPIConfigError, match="session_model"):
            CookieStrategy.from_config({"lifetime": 60})

    def test_guard_binds_its_name(self):
        s = CookieStrategy(FakeSession)
        Guard("admin", s, FakeUser)
        assert s._guard == "admin"


# ---------------------------------------------------------------------------
# Guard — configuration and dependencies
# ---------------------------------------------------------------------------

class TestGuardWithCookie:
    @pytest.fixture
    def strategy(self):
        return CookieStrategy(FakeSession, secure=False)

    @pytest.fixture
    def guard(self, strategy):
        return Guard(name="web", strategy=strategy, user_model=FakeUser)

    def test_guard_without_user_model_is_a_config_error(self, strategy):
        with pytest.raises(ForgeAPIConfigError, match="no user model"):
            Guard(name="web", strategy=strategy, user_model=None)

    def test_guard_requires_user_model_argument(self, strategy):
        with pytest.raises(TypeError):
            Guard(name="web", strategy=strategy)

    @pytest.mark.anyio
    async def test_missing_cookie_required_raises_401(self, guard):
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            await guard.authenticate(make_request(), required=True)
        assert exc.value.status_code == 401

    @pytest.mark.anyio
    async def test_missing_cookie_optional_returns_none(self, guard):
        result = await guard.authenticate(make_request(), required=False)
        assert result is None

    def test_current_user_returns_annotated(self, guard):
        dep = guard.current_user()
        assert dep is not None
        assert dep is guard.current_user()  # cached

    def test_optional_user_returns_annotated(self, guard):
        dep = guard.optional_user()
        assert dep is not None
        assert dep is guard.optional_user()  # cached

    @pytest.mark.anyio
    async def test_login_outside_a_request_is_a_config_error(self, guard):
        with pytest.raises(ForgeAPIConfigError, match="AuthMiddleware"):
            await guard.login(SimpleNamespace(id=1))


# ---------------------------------------------------------------------------
# Guard — TelegramStrategy has no sessions
# ---------------------------------------------------------------------------

class TestGuardTelegramUnsupported:
    @pytest.fixture
    def guard(self):
        from forgeapi.auth.strategies.telegram import TelegramStrategy
        return Guard("tg", TelegramStrategy(bot_token="123:abc"), FakeUser)

    @pytest.mark.anyio
    @pytest.mark.parametrize("operation", ["login", "logout", "logout_others"])
    async def test_session_operations_raise(self, guard, operation):
        user = SimpleNamespace(id=1)
        call = getattr(guard, operation)
        with pytest.raises(NotImplementedError):
            await (call() if operation == "logout" else call(user))


# ---------------------------------------------------------------------------
# Auth facade
# ---------------------------------------------------------------------------

class TestAuthFacade:
    @pytest.fixture
    def facade(self):
        a = fresh_auth()
        g = Guard(name="web", strategy=CookieStrategy(FakeSession, secure=False), user_model=FakeUser)
        a.register("web", g)
        a.set_default("web")
        return a

    def test_guard_returns_registered(self, facade):
        g = facade.guard("web")
        assert isinstance(g, Guard)
        assert g.name == "web"

    def test_unknown_guard_raises(self, facade):
        with pytest.raises(ForgeAPIConfigError):
            facade.guard("nonexistent")

    def test_multiple_guards_registered(self):
        a = fresh_auth()
        a.register("web", Guard("web", CookieStrategy(FakeSession, secure=False), FakeUser))
        a.register("admin", Guard("admin", CookieStrategy(FakeSession, cookie_name="admin", secure=False), FakeUser))
        assert a.guard("web").name == "web"
        assert a.guard("admin").name == "admin"


# ---------------------------------------------------------------------------
# Contracts
# ---------------------------------------------------------------------------

class TestContracts:
    def test_cookie_is_session_issuer(self):
        from forgeapi.auth.contracts import SessionIssuer
        assert isinstance(CookieStrategy(FakeSession, secure=False), SessionIssuer)

    def test_telegram_is_not_session_issuer(self):
        from forgeapi.auth.contracts import SessionIssuer
        from forgeapi.auth.strategies.telegram import TelegramStrategy
        s = TelegramStrategy(bot_token="1:x")
        assert not isinstance(s, SessionIssuer)


# ---------------------------------------------------------------------------
# Strategy factories — auth.extend()
# ---------------------------------------------------------------------------

class TestStrategyFactories:
    def test_create_builtin_cookie(self):
        a = fresh_auth()
        s = a.create_strategy("cookie", {"lifetime": 7200, "session_model": "tests.fakes.FakeSession"})
        assert isinstance(s, CookieStrategy)
        assert s._lifetime == 7200

    def test_unknown_strategy_raises(self):
        a = fresh_auth()
        with pytest.raises(ForgeAPIConfigError, match="Unknown auth strategy"):
            a.create_strategy("oauth99")

    def test_extend_registers_custom_strategy(self):
        from forgeapi.auth.strategies.base import AuthStrategy

        class ApiKeyStrategy(AuthStrategy):
            def __init__(self, header: str = "X-Api-Key"):
                self.header = header

            async def authenticate(self, request):
                return None

        a = fresh_auth()
        a.extend("apikey", ApiKeyStrategy)
        s = a.create_strategy("apikey", {"header": "X-Key"})
        assert isinstance(s, ApiKeyStrategy)
        assert s.header == "X-Key"


# ---------------------------------------------------------------------------
# Guard — error translation (HTTP boundary)
# ---------------------------------------------------------------------------

class TestGuardErrorTranslation:
    @pytest.fixture
    def guard(self):
        return Guard("web", CookieStrategy(FakeSession, secure=False), FakeUser)

    @pytest.mark.anyio
    async def test_missing_credentials_raises_401(self, guard):
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            await guard.authenticate(make_request(), required=True)
        assert exc.value.status_code == 401

    @pytest.mark.anyio
    async def test_cookie_strategy_has_no_challenge_header(self, guard):
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            await guard.authenticate(make_request(), required=True)
        assert not exc.value.headers or "WWW-Authenticate" not in exc.value.headers
