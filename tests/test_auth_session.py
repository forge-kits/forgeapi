"""Server-side sessions of the cookie strategy: the store, the strategy and login/logout through a real app."""
import hashlib
from datetime import timedelta

import httpx
import pytest
from fastapi import FastAPI, Request
from starlette.requests import Request as StarletteRequest
from tortoise import Tortoise, timezone
import tortoise.timezone as tt

from forgeapi.auth import AuthMiddleware
from forgeapi.auth import sessions as sessions_module
from forgeapi.auth.facade import Auth
from forgeapi.auth.guard import Guard
from forgeapi.auth.strategies.cookie import CookieStrategy
from forgeapi.exceptions import ForgeAPIConfigError, SessionExpiredError, SessionInvalidError
from tests.fakes import FakeSession, FakeUser


@pytest.fixture
async def sessions_db():
    await Tortoise.init(db_url="sqlite://:memory:", modules={"models": ["tests.fakes"]})
    await Tortoise.generate_schemas()
    yield
    await Tortoise.close_connections()
    tt._reset_timezone_cache()


def make_request(cookies: dict | None = None) -> StarletteRequest:
    headers = []
    if cookies:
        headers.append((b"cookie", "; ".join(f"{k}={v}" for k, v in cookies.items()).encode()))
    return StarletteRequest({
        "type": "http", "method": "GET", "path": "/", "query_string": b"",
        "headers": headers, "client": ("10.0.0.1", 5000),
    })


def make_app(**cookie_options):
    """An app with a login, a logout and a protected route, wired like Core(app) does it."""
    facade = Auth()
    facade.register("web", Guard("web", CookieStrategy(FakeSession, secure=False, **cookie_options), FakeUser))
    facade.set_default("web")
    app = FastAPI()
    app.add_middleware(AuthMiddleware)

    @app.post("/login/{user_id}")
    async def login(user_id: int):
        user = FakeUser.users.setdefault(str(user_id), FakeUser(user_id, f"user{user_id}"))
        await facade.login(user)
        return {"ok": True}

    @app.post("/logout")
    async def logout():
        await facade.logout()
        return {"ok": True}

    @app.get("/me")
    async def me(request: Request):
        user = await facade.guard().authenticate(request)
        return {"id": user.id}

    return app, facade


def client(app) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


# ---------------------------------------------------------------------------
# login and logout through the facade
# ---------------------------------------------------------------------------

async def test_login_sets_a_cookie_that_authenticates(sessions_db):
    # arrange
    app, _ = make_app()
    async with client(app) as http:
        # act
        login = await http.post("/login/1")
        me = await http.get("/me")
    # assert: the cookie came with the login response and the next request is authenticated
    assert "session=" in login.headers["set-cookie"]
    assert "HttpOnly" in login.headers["set-cookie"]
    assert me.status_code == 200 and me.json() == {"id": 1}


async def test_without_login_the_route_is_401(sessions_db):
    app, _ = make_app()
    async with client(app) as http:
        assert (await http.get("/me")).status_code == 401


async def test_logout_ends_the_session_on_the_server(sessions_db):
    app, _ = make_app()
    async with client(app) as http:
        login = await http.post("/login/1")
        stolen = login.cookies["session"]
        logout = await http.post("/logout")
        # the browser got an expiring cookie, and the copied cookie no longer works
        assert "Max-Age=0" in logout.headers["set-cookie"]
        assert await FakeSession.all().count() == 0
    async with client(app) as other:
        other.cookies.set("session", stolen)
        assert (await other.get("/me")).status_code == 401


async def test_the_table_keeps_only_the_hash_of_the_token(sessions_db):
    app, _ = make_app()
    async with client(app) as http:
        token = (await http.post("/login/1")).cookies["session"]
    row = await FakeSession.get()
    assert row.id == hashlib.sha256(token.encode()).hexdigest() != token
    assert row.user_id == "1" and row.guard == "web"


async def test_login_replaces_the_session_the_request_already_had(sessions_db):
    # a token set before the login must not survive it (session fixation)
    app, _ = make_app()
    async with client(app) as http:
        first = (await http.post("/login/1")).cookies["session"]
        second = (await http.post("/login/1")).cookies["session"]
    assert first != second
    assert await FakeSession.all().count() == 1


# ---------------------------------------------------------------------------
# expiry
# ---------------------------------------------------------------------------

async def test_idle_session_expires_and_is_deleted(sessions_db):
    app, _ = make_app()
    async with client(app) as http:
        await http.post("/login/1")
        await FakeSession.all().update(expires_at=timezone.now() - timedelta(seconds=1))
        assert (await http.get("/me")).status_code == 401
    assert await FakeSession.all().count() == 0


async def test_absolute_lifetime_ends_an_active_session(sessions_db):
    app, _ = make_app(absolute_lifetime=600)
    async with client(app) as http:
        await http.post("/login/1")
        assert (await http.get("/me")).status_code == 200
        await FakeSession.all().update(created_at=timezone.now() - timedelta(seconds=601))
        assert (await http.get("/me")).status_code == 401


async def test_activity_moves_the_expiry_forward_but_not_on_every_request(sessions_db):
    # arrange: a session that was last active a moment ago
    strategy = CookieStrategy(FakeSession, secure=False, lifetime=3600)
    token = await strategy._store.create(user_id="1", guard="default", lifetime=3600, request=make_request())
    row = await FakeSession.get()
    before = row.expires_at
    # act + assert: within TOUCH_INTERVAL nothing is written
    await strategy.authenticate(make_request({"session": token}))
    assert (await FakeSession.get()).expires_at == before
    # once the interval has passed the expiry slides forward
    old = timezone.now() - timedelta(seconds=sessions_module.TOUCH_INTERVAL + 1)
    await FakeSession.all().update(last_activity=old, expires_at=old + timedelta(seconds=3600))
    await strategy.authenticate(make_request({"session": token}))
    assert (await FakeSession.get()).expires_at > old + timedelta(seconds=3600)


# ---------------------------------------------------------------------------
# strategy
# ---------------------------------------------------------------------------

async def test_no_cookie_means_no_credentials(sessions_db):
    assert await CookieStrategy(FakeSession, secure=False).authenticate(make_request()) is None


async def test_unknown_token_is_invalid(sessions_db):
    with pytest.raises(SessionInvalidError):
        await CookieStrategy(FakeSession, secure=False).authenticate(make_request({"session": "never-issued"}))


async def test_expired_token_raises_expired(sessions_db):
    strategy = CookieStrategy(FakeSession, secure=False)
    token = await strategy._store.create(user_id="1", guard="default", lifetime=3600, request=make_request())
    await FakeSession.all().update(expires_at=timezone.now() - timedelta(seconds=1))
    with pytest.raises(SessionExpiredError):
        await strategy.authenticate(make_request({"session": token}))


async def test_a_session_of_one_guard_does_not_log_in_to_another(sessions_db):
    # user 1 and admin 1 share an id, so the guard must be part of the lookup
    web, admin = CookieStrategy(FakeSession, secure=False), CookieStrategy(FakeSession, secure=False)
    Guard("web", web, FakeUser)
    Guard("admin", admin, FakeUser)
    token = await web._store.create(user_id="1", guard="web", lifetime=3600, request=make_request())
    assert await web.authenticate(make_request({"session": token})) == "1"
    with pytest.raises(SessionInvalidError):
        await admin.authenticate(make_request({"session": token}))


async def test_store_records_ip_and_user_agent(sessions_db):
    request = StarletteRequest({
        "type": "http", "method": "GET", "path": "/", "query_string": b"",
        "headers": [(b"user-agent", b"Mozilla/5.0 test")], "client": ("10.0.0.1", 5000),
    })
    await CookieStrategy(FakeSession, secure=False)._store.create(user_id="7", guard="default", lifetime=60, request=request)
    row = await FakeSession.get()
    assert (row.ip_address, row.user_agent, row.user_id) == ("10.0.0.1", "Mozilla/5.0 test", "7")


# ---------------------------------------------------------------------------
# logging out other devices
# ---------------------------------------------------------------------------

async def test_logout_others_keeps_only_the_current_session(sessions_db):
    strategy = CookieStrategy(FakeSession, secure=False)
    request = make_request()
    mine = await strategy._store.create(user_id="1", guard="default", lifetime=60, request=request)
    await strategy._store.create(user_id="1", guard="default", lifetime=60, request=request)
    await strategy._store.create(user_id="2", guard="default", lifetime=60, request=request)

    removed = await strategy.logout_others(make_request({"session": mine}), "1")

    assert removed == 1
    assert await FakeSession.filter(user_id="1").count() == 1
    assert await FakeSession.filter(user_id="2").count() == 1   # another user is untouched
    assert await strategy.authenticate(make_request({"session": mine})) == "1"


async def test_prune_deletes_only_expired_sessions(sessions_db):
    strategy = CookieStrategy(FakeSession, secure=False)
    request = make_request()
    await strategy._store.create(user_id="1", guard="default", lifetime=60, request=request)
    await strategy._store.create(user_id="2", guard="default", lifetime=60, request=request)
    await FakeSession.filter(user_id="1").update(expires_at=timezone.now() - timedelta(seconds=1))
    assert await strategy._store.prune() == 1
    assert await FakeSession.all().count() == 1


async def test_unregistered_model_gives_hint(monkeypatch):
    # a model missing from TORTOISE_ORM keeps default_connection = None
    monkeypatch.setattr(FakeSession._meta, "default_connection", None)
    with pytest.raises(ForgeAPIConfigError) as exc:
        await CookieStrategy(FakeSession, secure=False).authenticate(make_request({"session": "x"}))
    assert "FakeSession" in (exc.value.hint or "")
