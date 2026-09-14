import pytest
from fastapi.responses import Response
from starlette.requests import Request

from forgeapi.auth.strategies.cookie import CookieStrategy
from forgeapi.exceptions import ForgeAPIConfigError, SessionInvalidError


SECRET = "cookie-test-secret"


@pytest.fixture
def strategy():
    return CookieStrategy(secret_key=SECRET, cookie_name="session")


def test_missing_secret_raises():
    import os
    os.environ.pop("COOKIE_SECRET", None)
    with pytest.raises(ForgeAPIConfigError, match="Cookie secret"):
        CookieStrategy()


def test_create_session_returns_string(strategy):
    value = strategy.create_session({"sub": "1", "username": "alice"})
    assert isinstance(value, str)
    assert "." in value


def test_set_cookie_writes_to_response(strategy):
    response = Response()
    strategy.set_cookie(response, {"sub": "1", "username": "alice"})
    assert "session" in response.headers.get("set-cookie", "")


def test_delete_cookie(strategy):
    response = Response()
    strategy.delete_cookie(response)
    assert "session" in response.headers.get("set-cookie", "")


def _make_request(cookie_name: str, cookie_value: str) -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "query_string": b"",
        "headers": [(b"cookie", f"{cookie_name}={cookie_value}".encode())],
    }
    return Request(scope)


async def test_authenticate_valid_cookie(strategy):
    value = strategy.create_session({"sub": "42", "username": "alice"})
    request = _make_request("session", value)
    user = await strategy.authenticate(request)
    assert user is not None
    assert user.id == "42"
    assert user.username == "alice"
    assert user.auth_method == "cookie"


async def test_authenticate_no_cookie(strategy):
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


async def test_authenticate_tampered_signature(strategy):
    value = strategy.create_session({"sub": "1"})
    payload, _ = value.rsplit(".", 1)
    tampered = f"{payload}.invalidsignature"
    request = _make_request("session", tampered)
    with pytest.raises(SessionInvalidError):
        await strategy.authenticate(request)


async def test_authenticate_malformed_cookie(strategy):
    request = _make_request("session", "notvalidatall")
    with pytest.raises(SessionInvalidError):
        await strategy.authenticate(request)


async def test_extra_fields_in_user(strategy):
    value = strategy.create_session({"sub": "1", "username": "alice", "role": "admin"})
    request = _make_request("session", value)
    user = await strategy.authenticate(request)
    assert user.extra.get("role") == "admin"
