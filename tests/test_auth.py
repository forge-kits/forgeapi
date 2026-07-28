"""Tests for auth: CookieStrategy, Guard, Auth facade."""
import time
import pytest
from starlette.requests import Request as StarletteRequest
from starlette.responses import Response as StarletteResponse

from forgeapi.auth.strategies.cookie import CookieStrategy
from forgeapi.auth.guard import Guard
from forgeapi.auth.facade import Auth
from forgeapi.auth.models import AuthUser
from forgeapi.exceptions import ForgeAPIConfigError, SessionExpiredError, SessionInvalidError


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
    def test_empty_secret_raises(self, monkeypatch):
        monkeypatch.delenv("COOKIE_SECRET", raising=False)
        with pytest.raises(ForgeAPIConfigError):
            CookieStrategy(secret_key="")

    def test_falls_back_to_env(self, monkeypatch):
        monkeypatch.setenv("COOKIE_SECRET", "env_secret_key_for_tests_!!")
        s = CookieStrategy()
        assert s._secret == "env_secret_key_for_tests_!!"

    def test_missing_env_raises(self, monkeypatch):
        monkeypatch.delenv("COOKIE_SECRET", raising=False)
        with pytest.raises(ForgeAPIConfigError):
            CookieStrategy()

    def test_custom_cookie_name(self):
        s = CookieStrategy(secret_key="s3cr3t_test_key_abcdef", cookie_name="auth")
        assert s._cookie_name == "auth"

    def test_from_config_reads_secret(self):
        s = CookieStrategy.from_config({"secret": "config_secret_key_tests!"})
        assert s._secret == "config_secret_key_tests!"

    def test_from_config_missing_secret_raises(self, monkeypatch):
        monkeypatch.delenv("COOKIE_SECRET", raising=False)
        with pytest.raises(ForgeAPIConfigError):
            CookieStrategy.from_config({})


# ---------------------------------------------------------------------------
# CookieStrategy — session round-trip
# ---------------------------------------------------------------------------

class TestCookieStrategySession:
    @pytest.fixture
    def strategy(self):
        return CookieStrategy(secret_key="roundtrip_secret_key_abc!", secure=False)

    def test_create_session_returns_signed_string(self, strategy):
        value = strategy.create_session({"sub": "42", "username": "alice"})
        assert "." in value

    @pytest.mark.anyio
    async def test_session_roundtrip_via_authenticate(self, strategy):
        value = strategy.create_session({"sub": "42", "username": "alice"})
        req = make_request(cookies={"session": value})
        user = await strategy.authenticate(req)
        assert user is not None
        assert user.id == "42"
        assert user.username == "alice"
        assert user.auth_method == "cookie"

    @pytest.mark.anyio
    async def test_tampered_signature_raises(self, strategy):
        value = strategy.create_session({"sub": "1"})
        payload = value.rsplit(".", 1)[0]
        req = make_request(cookies={"session": f"{payload}.INVALIDSIG"})
        with pytest.raises(SessionInvalidError):
            await strategy.authenticate(req)

    @pytest.mark.anyio
    async def test_expired_session_raises(self, strategy):
        import base64, json, hmac, hashlib
        data = {"sub": "1", "exp": int(time.time()) - 1}
        raw_payload = base64.urlsafe_b64encode(json.dumps(data).encode()).decode()
        sig_raw = hmac.new(strategy._secret.encode(), raw_payload.encode(), hashlib.sha256).digest()
        sig = base64.urlsafe_b64encode(sig_raw).decode().rstrip("=")
        req = make_request(cookies={"session": f"{raw_payload}.{sig}"})
        with pytest.raises(SessionExpiredError):
            await strategy.authenticate(req)

    @pytest.mark.anyio
    async def test_no_cookie_returns_none(self, strategy):
        req = make_request()
        result = await strategy.authenticate(req)
        assert result is None

    def test_set_cookie_writes_header(self, strategy):
        response = make_response()
        strategy.set_cookie(response, {"sub": "7", "username": "bob"})
        assert "session" in response.headers.get("set-cookie", "")

    def test_delete_cookie_clears_it(self, strategy):
        response = make_response()
        strategy.delete_cookie(response)
        assert "session" in response.headers.get("set-cookie", "")


# ---------------------------------------------------------------------------
# Guard — with CookieStrategy
# ---------------------------------------------------------------------------

class TestGuardWithCookie:
    @pytest.fixture
    def strategy(self):
        return CookieStrategy(secret_key="guard_secret_key_tests!!", secure=False)

    @pytest.fixture
    def guard(self, strategy):
        return Guard(name="web", strategy=strategy)

    @pytest.mark.anyio
    async def test_authenticate_valid_session(self, guard, strategy):
        value = strategy.create_session({"sub": "5", "username": "carol"})
        user = await guard.authenticate(make_request(cookies={"session": value}), required=True)
        assert isinstance(user, AuthUser)
        assert user.id == "5"

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

    @pytest.mark.anyio
    async def test_invalid_session_raises_401_even_when_optional(self, guard):
        from fastapi import HTTPException
        req = make_request(cookies={"session": "payload.BADSIG"})
        with pytest.raises(HTTPException) as exc:
            await guard.authenticate(req, required=False)
        assert exc.value.status_code == 401

    def test_current_user_returns_annotated(self, guard):
        dep = guard.current_user()
        assert dep is not None
        assert dep is guard.current_user()  # cached

    def test_optional_user_returns_annotated(self, guard):
        dep = guard.optional_user()
        assert dep is not None
        assert dep is guard.optional_user()  # cached

    def test_token_creates_session_value(self, guard, strategy):
        user = AuthUser(id="10", username="dave", auth_method="cookie")
        token = guard.token(user)
        assert "." in token

    def test_set_cookie_on_response(self, guard):
        response = make_response()
        guard.set_cookie(response, {"sub": "7"})
        assert "session" in response.headers.get("set-cookie", "")

    def test_delete_cookie_on_response(self, guard):
        response = make_response()
        guard.delete_cookie(response)
        assert "session" in response.headers.get("set-cookie", "")

    def test_payload_from_db_model(self, guard):
        class FakeUser:
            id = 42
            email = "test@example.com"

        payload = guard._build_payload(FakeUser())
        assert payload["sub"] == "42"


# ---------------------------------------------------------------------------
# Guard — TelegramStrategy raises for session methods
# ---------------------------------------------------------------------------

class TestGuardTelegramUnsupported:
    @pytest.fixture
    def guard(self):
        from forgeapi.auth.strategies.telegram import TelegramStrategy
        return Guard("tg", TelegramStrategy(bot_token="123:abc"))

    def test_token_raises(self, guard):
        user = AuthUser(id="1", auth_method="telegram")
        with pytest.raises(NotImplementedError):
            guard.token(user)

    def test_set_cookie_raises(self, guard):
        with pytest.raises(NotImplementedError):
            guard.set_cookie(make_response(), {"sub": "1"})

    def test_delete_cookie_raises(self, guard):
        with pytest.raises(NotImplementedError):
            guard.delete_cookie(make_response())


# ---------------------------------------------------------------------------
# Auth facade
# ---------------------------------------------------------------------------

class TestAuthFacade:
    @pytest.fixture
    def facade(self):
        a = fresh_auth()
        strategy = CookieStrategy(secret_key="facade_secret_key_tests!!", secure=False)
        g = Guard(name="web", strategy=strategy)
        a.register("web", g)
        a.set_default("web")
        return a, strategy

    def test_guard_returns_registered(self, facade):
        a, _ = facade
        g = a.guard("web")
        assert isinstance(g, Guard)
        assert g.name == "web"

    def test_unknown_guard_raises(self, facade):
        a, _ = facade
        with pytest.raises(ForgeAPIConfigError):
            a.guard("nonexistent")

    def test_set_cookie_shortcut(self, facade):
        a, _ = facade
        response = make_response()
        a.set_cookie(response, {"sub": "1"})
        assert "session" in response.headers.get("set-cookie", "")

    def test_multiple_guards_registered(self):
        a = fresh_auth()
        s1 = CookieStrategy(secret_key="guard1_secret_key_tests!!!", secure=False)
        s2 = CookieStrategy(secret_key="guard2_secret_key_tests!!!", cookie_name="admin", secure=False)
        a.register("web", Guard("web", s1))
        a.register("admin", Guard("admin", s2))
        assert a.guard("web").name == "web"
        assert a.guard("admin").name == "admin"


# ---------------------------------------------------------------------------
# Contracts
# ---------------------------------------------------------------------------

class TestContracts:
    def test_cookie_is_session_issuer(self):
        from forgeapi.auth.contracts import SessionIssuer
        s = CookieStrategy(secret_key="contract_secret_key_tests!!", secure=False)
        assert isinstance(s, SessionIssuer)

    def test_telegram_is_not_session_issuer(self):
        from forgeapi.auth.contracts import SessionIssuer
        from forgeapi.auth.strategies.telegram import TelegramStrategy
        s = TelegramStrategy(bot_token="1:x")
        assert not isinstance(s, SessionIssuer)

    def test_custom_session_issuer_works_with_guard(self):
        from forgeapi.auth.strategies.base import AuthStrategy

        class StubStrategy(AuthStrategy):
            async def authenticate(self, request):
                return None

            def create_session(self, data: dict) -> str:
                return f"stub:{data['sub']}"

            def set_cookie(self, response, data: dict) -> None:
                pass

            def delete_cookie(self, response) -> None:
                pass

        g = Guard("stub", StubStrategy())
        user = AuthUser(id="7", auth_method="stub")
        assert g.token(user) == "stub:7"


# ---------------------------------------------------------------------------
# Strategy factories — auth.extend()
# ---------------------------------------------------------------------------

class TestStrategyFactories:
    def test_create_builtin_cookie(self):
        a = fresh_auth()
        s = a.create_strategy("cookie", {"secret": "factory_secret_key_tests!!"})
        assert isinstance(s, CookieStrategy)

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
# auth_claims() hook
# ---------------------------------------------------------------------------

class TestAuthClaims:
    def test_model_controls_claims(self):
        strategy = CookieStrategy(secret_key="claims_secret_key_tests!!", secure=False)
        g = Guard("web", strategy)

        class User:
            id = 42

            def auth_claims(self) -> dict:
                return {"username": "alice", "role": "admin"}

        session = g.token(User())
        assert "." in session

    def test_default_payload_uses_id_and_username(self):
        strategy = CookieStrategy(secret_key="payload_secret_key_tests!", secure=False)
        g = Guard("web", strategy)

        class User:
            id = 99
            username = "bob"

        payload = g._build_payload(User())
        assert payload["sub"] == "99"
        assert payload.get("username") == "bob"


# ---------------------------------------------------------------------------
# Guard — error translation (HTTP boundary)
# ---------------------------------------------------------------------------

class TestGuardErrorTranslation:
    @pytest.fixture
    def guard(self):
        return Guard("web", CookieStrategy(secret_key="error_secret_key_tests!!", secure=False))

    @pytest.mark.anyio
    async def test_expired_session_translates_to_401(self, guard, guard_strategy=None):
        import base64, json, hmac, hashlib
        secret = guard._strategy._secret
        data = {"sub": "1", "exp": int(time.time()) - 1}
        raw = base64.urlsafe_b64encode(json.dumps(data).encode()).decode()
        sig = base64.urlsafe_b64encode(
            hmac.new(secret.encode(), raw.encode(), hashlib.sha256).digest()
        ).decode().rstrip("=")
        from fastapi import HTTPException
        req = make_request(cookies={"session": f"{raw}.{sig}"})
        with pytest.raises(HTTPException) as exc:
            await guard.authenticate(req, required=True)
        assert exc.value.status_code == 401

    @pytest.mark.anyio
    async def test_invalid_session_translates_to_401(self, guard):
        from fastapi import HTTPException
        req = make_request(cookies={"session": "payload.BADSIG"})
        with pytest.raises(HTTPException) as exc:
            await guard.authenticate(req, required=True)
        assert exc.value.status_code == 401

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
