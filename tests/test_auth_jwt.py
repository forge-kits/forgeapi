import pytest
from starlette.requests import Request

from forgeapi.auth.strategies.jwt import JWTStrategy
from forgeapi.exceptions import ForgeAPIConfigError, TokenExpiredError, TokenInvalidError


SECRET = "test-secret-key"


@pytest.fixture
def strategy():
    return JWTStrategy(secret_key=SECRET, access_token_expire_minutes=30)


def test_missing_secret_raises():
    import os
    os.environ.pop("JWT_SECRET", None)
    with pytest.raises(ForgeAPIConfigError, match="JWT secret"):
        JWTStrategy()


def test_create_access_token(strategy):
    token = strategy.create_access_token({"sub": "42", "username": "alice"})
    assert isinstance(token, str)
    assert len(token) > 0


def test_create_refresh_token(strategy):
    token = strategy.create_refresh_token({"sub": "42"})
    assert isinstance(token, str)


def test_decode_valid_token(strategy):
    token = strategy.create_access_token({"sub": "42", "username": "alice"})
    payload = strategy.decode(token)
    assert payload["sub"] == "42"
    assert payload["username"] == "alice"
    assert payload["type"] == "access"


def test_decode_refresh_token_type(strategy):
    token = strategy.create_refresh_token({"sub": "42"})
    payload = strategy.decode(token)
    assert payload["type"] == "refresh"


def test_decode_expired_token():
    s = JWTStrategy(secret_key=SECRET, access_token_expire_minutes=-1)
    token = s.create_access_token({"sub": "1"})
    with pytest.raises(TokenExpiredError) as exc:
        s.decode(token)
    assert "expired" in str(exc.value).lower()


def test_decode_invalid_token(strategy):
    with pytest.raises(TokenInvalidError):
        strategy.decode("not.a.valid.token")


def test_extra_claims_preserved(strategy):
    token = strategy.create_access_token({"sub": "1", "role": "admin", "org": "acme"})
    payload = strategy.decode(token)
    assert payload["role"] == "admin"
    assert payload["org"] == "acme"


async def test_authenticate_with_bearer(strategy):
    token = strategy.create_access_token({"sub": "42", "username": "alice"})
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "query_string": b"",
        "headers": [(b"authorization", f"Bearer {token}".encode())],
    }
    request = Request(scope)
    user = await strategy.authenticate(request)
    assert user is not None
    assert user.id == "42"
    assert user.username == "alice"
    assert user.auth_method == "jwt"


async def test_authenticate_no_header(strategy):
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "query_string": b"",
        "headers": [],
    }
    request = Request(scope)
    user = await strategy.authenticate(request)
    assert user is None


async def test_authenticate_extra_in_user(strategy):
    token = strategy.create_access_token({"sub": "1", "role": "admin"})
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "query_string": b"",
        "headers": [(b"authorization", f"Bearer {token}".encode())],
    }
    request = Request(scope)
    user = await strategy.authenticate(request)
    assert user.extra.get("role") == "admin"
