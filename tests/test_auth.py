"""Tests for auth: JWTStrategy, Guard, Auth facade."""
import pytest
from datetime import datetime, timedelta, timezone
from starlette.requests import Request as StarletteRequest

from forgeapi.auth.strategies.jwt import JWTStrategy
from forgeapi.auth.guard import Guard
from forgeapi.auth.facade import Auth
from forgeapi.auth.models import AuthUser
from forgeapi.exceptions import ForgeAPIConfigError, TokenExpiredError, TokenInvalidError

import jwt as _jwt


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_request(headers: dict | None = None) -> StarletteRequest:
    raw = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    return StarletteRequest({
        "type": "http", "method": "GET", "path": "/",
        "headers": raw, "query_string": b"",
    })


def fresh_auth() -> Auth:
    """Return a clean Auth facade not shared with the global singleton."""
    return Auth()


# ---------------------------------------------------------------------------
# JWTStrategy — construction
# ---------------------------------------------------------------------------

class TestJWTStrategyConstruction:
    def test_empty_secret_raises(self, monkeypatch):
        monkeypatch.delenv("JWT_SECRET", raising=False)
        with pytest.raises(ForgeAPIConfigError, match="JWT secret"):
            JWTStrategy(secret_key="")

    def test_falls_back_to_env(self, monkeypatch):
        monkeypatch.setenv("JWT_SECRET", "env_secret")
        assert JWTStrategy()._secret == "env_secret"

    def test_invalid_algorithm_raises(self):
        with pytest.raises(ForgeAPIConfigError, match="algorithm"):
            JWTStrategy(secret_key="secret", algorithm="RS256")

    def test_valid_algorithms_accepted(self):
        for alg in ("HS256", "HS384", "HS512"):
            assert JWTStrategy(secret_key="secret", algorithm=alg)._algorithm == alg


# ---------------------------------------------------------------------------
# JWTStrategy — token round-trip
# ---------------------------------------------------------------------------

class TestJWTStrategyTokens:
    @pytest.fixture
    def strategy(self):
        return JWTStrategy(secret_key="test_secret_key_for_unit_tests!!")

    def test_access_token_roundtrip(self, strategy):
        token = strategy.create_access_token({"sub": "42", "username": "alice"})
        payload = strategy.decode(token)
        assert payload["sub"] == "42"
        assert payload["username"] == "alice"
        assert payload["type"] == "access"

    def test_refresh_token_roundtrip(self, strategy):
        token = strategy.create_refresh_token({"sub": "42"})
        payload = strategy.decode(token)
        assert payload["sub"] == "42"
        assert payload["type"] == "refresh"

    def test_expected_type_mismatch_raises(self, strategy):
        token = strategy.create_access_token({"sub": "1"})
        with pytest.raises(TokenInvalidError, match="type"):
            strategy.decode(token, expected_type="refresh")

    def test_expired_token_raises(self, strategy):
        expired = datetime.now(timezone.utc) - timedelta(seconds=1)
        raw = _jwt.encode(
            {"sub": "1", "exp": expired, "type": "access"},
            "test_secret_key_for_unit_tests!!",
            algorithm="HS256",
        )
        with pytest.raises(TokenExpiredError):
            strategy.decode(raw)

    def test_tampered_token_raises(self, strategy):
        token = strategy.create_access_token({"sub": "1"})
        header_payload = ".".join(token.split(".")[:2])
        with pytest.raises(TokenInvalidError):
            strategy.decode(f"{header_payload}.AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA")

    def test_wrong_secret_raises(self, strategy):
        other = JWTStrategy(secret_key="different_secret_for_unit_tests!")
        token = other.create_access_token({"sub": "1"})
        with pytest.raises(TokenInvalidError):
            strategy.decode(token)


# ---------------------------------------------------------------------------
# JWTStrategy — authenticate (HTTP)
# ---------------------------------------------------------------------------

class TestJWTAuthenticate:
    @pytest.fixture
    def strategy(self):
        return JWTStrategy(secret_key="http_secret_key_for_unit_tests!!!")

    async def test_valid_bearer_returns_user(self, strategy):
        token = strategy.create_access_token({"sub": "7", "username": "bob"})
        user = await strategy.authenticate(make_request({"Authorization": f"Bearer {token}"}))
        assert user is not None
        assert user.id == "7"
        assert user.username == "bob"
        assert user.auth_method == "jwt"

    async def test_no_bearer_returns_none(self, strategy):
        assert await strategy.authenticate(make_request()) is None


# ---------------------------------------------------------------------------
# Guard — without DB model (AuthUser only)
# ---------------------------------------------------------------------------

class TestGuardNoModel:
    @pytest.fixture
    def strategy(self):
        return JWTStrategy(secret_key="guard_secret_key_for_tests!!!!!!")

    @pytest.fixture
    def guard(self, strategy):
        return Guard(name="api", strategy=strategy)

    async def test_authenticate_valid_token(self, guard, strategy):
        token = strategy.create_access_token({"sub": "5", "username": "carol"})
        user = await guard.authenticate(
            make_request({"Authorization": f"Bearer {token}"}), required=True
        )
        assert isinstance(user, AuthUser)
        assert user.id == "5"

    async def test_authenticate_missing_token_raises_401(self, guard):
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            await guard.authenticate(make_request(), required=True)
        assert exc.value.status_code == 401

    async def test_optional_missing_returns_none(self, guard):
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

    def test_token_creates_jwt(self, guard, strategy):
        user = AuthUser(id="10", username="dave", auth_method="jwt")
        token = guard.token(user)
        payload = strategy.decode(token)
        assert payload["sub"] == "10"

    def test_refresh_token_creates_refresh(self, guard, strategy):
        user = AuthUser(id="10", username="dave", auth_method="jwt")
        token = guard.refresh_token(user)
        payload = strategy.decode(token, expected_type="refresh")
        assert payload["sub"] == "10"

    def test_decode_delegates_to_strategy(self, guard, strategy):
        token = strategy.create_access_token({"sub": "99"})
        payload = guard.decode(token)
        assert payload["sub"] == "99"

    def test_payload_from_db_model(self, guard):
        class FakeUser:
            id = 42
            email = "test@example.com"

        payload = guard._build_payload(FakeUser())
        assert payload["sub"] == "42"
        assert payload.get("email") == "test@example.com"


# ---------------------------------------------------------------------------
# Auth facade
# ---------------------------------------------------------------------------

class TestAuthFacade:
    @pytest.fixture
    def facade(self):
        a = fresh_auth()
        strategy = JWTStrategy(secret_key="facade_secret_key_for_tests!!!")
        g = Guard(name="api", strategy=strategy)
        a.register("api", g)
        a.set_default("api")
        return a, strategy

    def test_guard_returns_registered(self, facade):
        a, _ = facade
        g = a.guard("api")
        assert isinstance(g, Guard)
        assert g.name == "api"

    def test_unknown_guard_raises(self, facade):
        a, _ = facade
        with pytest.raises(ForgeAPIConfigError):
            a.guard("nonexistent")

    def test_token_shortcut(self, facade):
        a, strategy = facade
        user = AuthUser(id="1", username="x", auth_method="jwt")
        token = a.token(user)
        payload = strategy.decode(token)
        assert payload["sub"] == "1"

    def test_refresh_token_shortcut(self, facade):
        a, strategy = facade
        user = AuthUser(id="2", username="y", auth_method="jwt")
        token = a.refresh_token(user)
        payload = strategy.decode(token, expected_type="refresh")
        assert payload["sub"] == "2"

    def test_decode_shortcut(self, facade):
        a, strategy = facade
        raw = strategy.create_access_token({"sub": "7"})
        payload = a.decode(raw)
        assert payload["sub"] == "7"

    def test_named_guard_token(self, facade):
        a, strategy = facade
        admin_strategy = JWTStrategy(secret_key="admin_guard_secret_key_tests!")
        admin_guard = Guard(name="admin", strategy=admin_strategy)
        a.register("admin", admin_guard)

        user = AuthUser(id="99", username="admin", auth_method="jwt")
        token = a.token(user, guard="admin")
        payload = admin_strategy.decode(token)
        assert payload["sub"] == "99"

    def test_multiple_guards_isolated(self):
        a = fresh_auth()
        s1 = JWTStrategy(secret_key="guard1_secret_key_for_isolation_test!")
        s2 = JWTStrategy(secret_key="guard2_secret_key_for_isolation_test!")
        a.register("api", Guard("api", s1))
        a.register("admin", Guard("admin", s2))
        a.set_default("api")

        user = AuthUser(id="1", username="u", auth_method="jwt")
        token = a.token(user, guard="api")

        # api guard decodes correctly
        payload = a.decode(token, guard="api")
        assert payload["sub"] == "1"

        # admin guard with different secret cannot decode api token
        with pytest.raises(TokenInvalidError):
            a.decode(token, guard="admin")


# ---------------------------------------------------------------------------
# Guard — domain-error → HTTP translation (single point)
# ---------------------------------------------------------------------------

class TestGuardErrorTranslation:
    @pytest.fixture
    def strategy(self):
        return JWTStrategy(secret_key="translation_secret_key_tests!!!!")

    @pytest.fixture
    def guard(self, strategy):
        return Guard(name="api", strategy=strategy)

    async def test_expired_token_translates_to_401(self, guard):
        from fastapi import HTTPException
        expired = _jwt.encode(
            {"sub": "1", "exp": datetime.now(timezone.utc) - timedelta(seconds=1), "type": "access"},
            "translation_secret_key_tests!!!!",
            algorithm="HS256",
        )
        with pytest.raises(HTTPException) as exc:
            await guard.authenticate(
                make_request({"Authorization": f"Bearer {expired}"}), required=True
            )
        assert exc.value.status_code == 401
        assert 'error="token_expired"' in exc.value.headers["WWW-Authenticate"]

    async def test_invalid_token_translates_to_401(self, guard):
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            await guard.authenticate(
                make_request({"Authorization": "Bearer not.a.token"}), required=True
            )
        assert exc.value.status_code == 401
        assert 'error="token_invalid"' in exc.value.headers["WWW-Authenticate"]

    async def test_invalid_token_raises_even_when_optional(self, guard):
        """Present-but-invalid credentials are a client bug — 401, not None."""
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            await guard.authenticate(
                make_request({"Authorization": "Bearer not.a.token"}), required=False
            )
        assert exc.value.status_code == 401

    async def test_missing_credentials_has_challenge_header(self, guard):
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            await guard.authenticate(make_request(), required=True)
        assert exc.value.headers["WWW-Authenticate"].startswith("Bearer")

    async def test_cookie_strategy_omits_challenge_header(self):
        from fastapi import HTTPException
        from forgeapi.auth.strategies.cookie import CookieStrategy
        g = Guard("web", CookieStrategy(secret_key="cookie_translation_secret!!"))
        with pytest.raises(HTTPException) as exc:
            await g.authenticate(make_request(), required=True)
        assert not exc.value.headers or "WWW-Authenticate" not in exc.value.headers


# ---------------------------------------------------------------------------
# Capability contracts — protocol dispatch instead of isinstance-on-class
# ---------------------------------------------------------------------------

class TestContracts:
    def test_jwt_capabilities(self):
        from forgeapi.auth.contracts import TokenIssuer, RefreshCapable, SessionIssuer
        s = JWTStrategy(secret_key="contract_check_secret_key!!!!!!!")
        assert isinstance(s, TokenIssuer)
        assert isinstance(s, RefreshCapable)
        assert not isinstance(s, SessionIssuer)

    def test_cookie_capabilities(self):
        from forgeapi.auth.contracts import TokenIssuer, RefreshCapable, SessionIssuer
        from forgeapi.auth.strategies.cookie import CookieStrategy
        s = CookieStrategy(secret_key="contract_check_cookie_secret!!")
        assert isinstance(s, SessionIssuer)
        assert not isinstance(s, TokenIssuer)
        assert not isinstance(s, RefreshCapable)

    def test_custom_token_issuer_works_with_guard(self):
        """A custom strategy implementing TokenIssuer gets guard.token() for free."""
        from forgeapi.auth.strategies.base import AuthStrategy

        class StubStrategy(AuthStrategy):
            async def authenticate(self, request):
                return None

            def create_access_token(self, payload: dict) -> str:
                return f"stub:{payload['sub']}"

            def decode(self, token, *, expected_type=None):
                return {"sub": token.removeprefix("stub:")}

        g = Guard("stub", StubStrategy())
        user = AuthUser(id="7", auth_method="stub")
        assert g.token(user) == "stub:7"
        assert g.decode("stub:7") == {"sub": "7"}

    def test_unsupported_capability_raises(self):
        from forgeapi.auth.strategies.telegram import TelegramStrategy
        g = Guard("tg", TelegramStrategy(bot_token="1:x"))
        user = AuthUser(id="1", auth_method="telegram")
        with pytest.raises(NotImplementedError):
            g.token(user)
        with pytest.raises(NotImplementedError):
            g.refresh_token(user)
        with pytest.raises(NotImplementedError):
            g.set_cookie(None, {})


# ---------------------------------------------------------------------------
# Strategy factories — from_config + auth.extend()
# ---------------------------------------------------------------------------

class TestStrategyFactories:
    def test_create_builtin_jwt(self):
        a = fresh_auth()
        s = a.create_strategy("jwt", {"secret": "factory_secret_key_for_tests!!", "access_ttl": 5})
        assert isinstance(s, JWTStrategy)
        assert s._access_ttl == 5

    def test_jwt_from_config_custom_env(self, monkeypatch):
        monkeypatch.setenv("MY_JWT", "env_factory_secret_for_tests!!!")
        s = JWTStrategy.from_config({"secret_env": "MY_JWT"})
        assert s._secret == "env_factory_secret_for_tests!!!"

    def test_jwt_from_config_missing_secret_names_env(self, monkeypatch):
        monkeypatch.delenv("CUSTOM_SECRET", raising=False)
        with pytest.raises(ForgeAPIConfigError, match="CUSTOM_SECRET"):
            JWTStrategy.from_config({"secret_env": "CUSTOM_SECRET"})

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
        strategy = JWTStrategy(secret_key="claims_hook_secret_key_tests!!!")
        g = Guard("api", strategy)

        class User:
            id = 42
            email = "ignored@example.com"

            def auth_claims(self) -> dict:
                return {"username": "alice", "role": "admin"}

        payload = strategy.decode(g.token(User()))
        assert payload["sub"] == "42"
        assert payload["role"] == "admin"
        assert "email" not in payload
