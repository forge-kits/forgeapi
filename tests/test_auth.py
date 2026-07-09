"""Tests for the auth module: JWTStrategy, AuthBackend, global backend."""
import pytest
import httpx
from datetime import datetime, timedelta, timezone
from fastapi import FastAPI
from unittest.mock import AsyncMock, MagicMock

from forgeapi.auth.strategies.jwt import JWTStrategy
from forgeapi.auth.backend import AuthBackend, set_global_backend
from forgeapi.auth.models import AuthUser
from forgeapi.exceptions import ForgeAPIConfigError, TokenExpiredError, TokenInvalidError

import jwt as _jwt


# ---------------------------------------------------------------------------
# Reset global backend between tests
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_global_backend():
    import forgeapi.auth.backend as _backend_mod
    original = _backend_mod._global_backend
    yield
    _backend_mod._global_backend = original


# ---------------------------------------------------------------------------
# JWTStrategy — construction
# ---------------------------------------------------------------------------

class TestJWTStrategyConstruction:
    def test_empty_secret_raises(self, monkeypatch):
        monkeypatch.delenv("JWT_SECRET", raising=False)
        with pytest.raises(ForgeAPIConfigError, match="JWT secret"):
            JWTStrategy(secret_key="")

    def test_none_secret_falls_back_to_env(self, monkeypatch):
        monkeypatch.setenv("JWT_SECRET", "env_secret")
        strategy = JWTStrategy()
        assert strategy._secret == "env_secret"

    def test_invalid_algorithm_raises(self):
        with pytest.raises(ForgeAPIConfigError, match="algorithm"):
            JWTStrategy(secret_key="secret", algorithm="RS256")

    def test_valid_algorithms_accepted(self):
        for alg in ("HS256", "HS384", "HS512"):
            s = JWTStrategy(secret_key="secret", algorithm=alg)
            assert s._algorithm == alg


# ---------------------------------------------------------------------------
# JWTStrategy — token round-trip
# ---------------------------------------------------------------------------

class TestJWTStrategyTokens:
    @pytest.fixture
    def strategy(self):
        return JWTStrategy(secret_key="test_secret_key_for_unit_tests!!")

    def test_create_and_decode_access_token(self, strategy):
        token = strategy.create_access_token({"sub": "42", "username": "alice"})
        payload = strategy.decode(token)
        assert payload["sub"] == "42"
        assert payload["username"] == "alice"
        assert payload["type"] == "access"

    def test_create_and_decode_refresh_token(self, strategy):
        token = strategy.create_refresh_token({"sub": "42"})
        payload = strategy.decode(token)
        assert payload["sub"] == "42"
        assert payload["type"] == "refresh"

    def test_expected_type_access_passes(self, strategy):
        token = strategy.create_access_token({"sub": "1"})
        payload = strategy.decode(token, expected_type="access")
        assert payload["type"] == "access"

    def test_wrong_expected_type_raises(self, strategy):
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
        # Replace the signature with clearly invalid bytes
        header_payload = ".".join(token.split(".")[:2])
        bad_token = f"{header_payload}.AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
        with pytest.raises(TokenInvalidError):
            strategy.decode(bad_token)

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

    @pytest.mark.anyio
    async def test_valid_bearer_returns_user(self, strategy):
        token = strategy.create_access_token({"sub": "7", "username": "bob"})
        app = FastAPI()

        @app.get("/me")
        async def me():
            from fastapi import Request
            pass

        # Build a request with the Bearer header
        from starlette.requests import Request as StarletteRequest
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [(b"authorization", f"Bearer {token}".encode())],
            "query_string": b"",
        }
        request = StarletteRequest(scope)
        user = await strategy.authenticate(request)
        assert user is not None
        assert user.id == "7"
        assert user.username == "bob"
        assert user.auth_method == "jwt"

    @pytest.mark.anyio
    async def test_no_bearer_returns_none(self, strategy):
        from starlette.requests import Request as StarletteRequest
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [],
            "query_string": b"",
        }
        request = StarletteRequest(scope)
        user = await strategy.authenticate(request)
        assert user is None


# ---------------------------------------------------------------------------
# AuthBackend
# ---------------------------------------------------------------------------

class TestAuthBackend:
    @pytest.fixture
    def backend(self):
        strategy = JWTStrategy(secret_key="backend_secret_key_for_tests!!!!")
        return AuthBackend(strategy=strategy)

    def test_strategy_property(self, backend):
        assert isinstance(backend.strategy, JWTStrategy)

    @pytest.mark.anyio
    async def test_current_user_returns_annotated_type(self, backend):
        cu = backend.current_user()
        # Annotated type — should be usable as a FastAPI dependency type
        assert cu is not None

    @pytest.mark.anyio
    async def test_resolve_required_raises_401_when_no_user(self, backend):
        from starlette.requests import Request as StarletteRequest
        from fastapi import HTTPException
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [],
            "query_string": b"",
        }
        request = StarletteRequest(scope)
        with pytest.raises(HTTPException) as exc_info:
            await backend._resolve_user(request, required=True)
        assert exc_info.value.status_code == 401

    @pytest.mark.anyio
    async def test_resolve_optional_returns_none_when_no_user(self, backend):
        from starlette.requests import Request as StarletteRequest
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [],
            "query_string": b"",
        }
        request = StarletteRequest(scope)
        result = await backend._resolve_user(request, required=False)
        assert result is None


# ---------------------------------------------------------------------------
# Global backend
# ---------------------------------------------------------------------------

class TestGlobalBackend:
    def test_get_global_before_set_raises(self):
        import forgeapi.auth.backend as _backend_mod
        _backend_mod._global_backend = None
        from forgeapi.auth.backend import _get_global_backend
        with pytest.raises(ForgeAPIConfigError, match="not configured"):
            _get_global_backend()

    def test_set_global_backend(self):
        strategy = JWTStrategy(secret_key="global_secret_key_for_unit_tests!")
        backend = AuthBackend(strategy=strategy)
        set_global_backend(backend)
        from forgeapi.auth.backend import _get_global_backend
        assert _get_global_backend() is backend

    @pytest.mark.anyio
    async def test_global_optional_user_returns_none_when_not_set(self):
        import forgeapi.auth.backend as _backend_mod
        _backend_mod._global_backend = None
        from forgeapi.auth.backend import _global_optional_user
        from starlette.requests import Request as StarletteRequest
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [],
            "query_string": b"",
        }
        request = StarletteRequest(scope)
        result = await _global_optional_user(request)
        assert result is None
