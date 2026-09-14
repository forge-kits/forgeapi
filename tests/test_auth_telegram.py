import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

import pytest
from starlette.requests import Request

from forgeapi.auth.strategies.telegram import TelegramStrategy
from forgeapi.exceptions import TokenExpiredError, TokenInvalidError


BOT_TOKEN = "123456:ABC-test-token"


def _make_init_data(user: dict, bot_token: str = BOT_TOKEN, age: int = 0) -> str:
    auth_date = int(time.time()) - age
    params = {
        "auth_date": str(auth_date),
        "user": json.dumps(user, separators=(",", ":")),
    }
    data_check = "\n".join(f"{k}={v}" for k, v in sorted(params.items()))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    hash_ = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()
    params["hash"] = hash_
    return urlencode(params)


@pytest.fixture
def strategy():
    return TelegramStrategy(bot_token=BOT_TOKEN, max_age_seconds=86400)


USER = {"id": 123456, "username": "alice", "first_name": "Alice", "language_code": "en"}


def test_valid_init_data(strategy):
    init_data = _make_init_data(USER)
    user = strategy.validate_init_data(init_data)
    assert user.id == 123456
    assert user.username == "alice"
    assert user.first_name == "Alice"


def test_missing_hash_raises(strategy):
    init_data = urlencode({"auth_date": str(int(time.time())), "user": json.dumps(USER)})
    with pytest.raises(TokenInvalidError) as exc:
        strategy.validate_init_data(init_data)
    assert "hash" in str(exc.value).lower()


def test_expired_data_raises():
    s = TelegramStrategy(bot_token=BOT_TOKEN, max_age_seconds=60)
    init_data = _make_init_data(USER, age=120)
    with pytest.raises(TokenExpiredError) as exc:
        s.validate_init_data(init_data)
    assert "expired" in str(exc.value).lower()


def test_debug_skips_expiry():
    s = TelegramStrategy(bot_token=BOT_TOKEN, max_age_seconds=60, debug=True)
    init_data = _make_init_data(USER, age=9999)
    user = s.validate_init_data(init_data)
    assert user.id == USER["id"]


def test_invalid_signature_raises(strategy):
    init_data = _make_init_data(USER)
    tampered = init_data.replace("hash=", "hash=x")
    with pytest.raises(TokenInvalidError):
        strategy.validate_init_data(tampered)


def test_multi_token_second_token_valid():
    other_token = "999:OTHER-token"
    s = TelegramStrategy(bot_token=[BOT_TOKEN, other_token])
    init_data = _make_init_data(USER, bot_token=other_token)
    user = s.validate_init_data(init_data)
    assert user.id == USER["id"]


def test_auth_date_and_language_code(strategy):
    init_data = _make_init_data(USER)
    user = strategy.validate_init_data(init_data)
    assert user.language_code == "en"
    assert isinstance(user.auth_date, int)


def _make_request(headers: list[tuple[bytes, bytes]]) -> Request:
    return Request({
        "type": "http",
        "method": "GET",
        "path": "/",
        "query_string": b"",
        "headers": headers,
    })


async def test_authenticate_x_header(strategy):
    init_data = _make_init_data(USER)
    request = _make_request([(b"x-telegram-init-data", init_data.encode())])
    user = await strategy.authenticate(request)
    assert user is not None
    assert user.id == 123456
    assert user.auth_method == "telegram"


async def test_authenticate_tma_header(strategy):
    init_data = _make_init_data(USER)
    request = _make_request([(b"authorization", f"tma {init_data}".encode())])
    user = await strategy.authenticate(request)
    assert user is not None
    assert user.id == 123456


async def test_authenticate_no_header(strategy):
    request = _make_request([])
    user = await strategy.authenticate(request)
    assert user is None


async def test_authenticate_extra_fields(strategy):
    init_data = _make_init_data(USER)
    request = _make_request([(b"x-telegram-init-data", init_data.encode())])
    user = await strategy.authenticate(request)
    assert user.extra["first_name"] == "Alice"
    assert user.extra["language_code"] == "en"
