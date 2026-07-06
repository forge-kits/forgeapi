import pytest
import httpx
from fastapi import FastAPI

from forgeapi.middleware.request_id import RequestIDMiddleware
from forgeapi.middleware.rate_limit import RateLimitMiddleware
from forgeapi.middleware.logging import LoggingMiddleware
from forgeapi.middleware.base_middleware import Middleware


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_app(*middleware_args):
    app = FastAPI()

    @app.get("/ping")
    async def ping():
        return {"ok": True}

    for mw, kwargs in middleware_args:
        app.add_middleware(mw, **kwargs)

    return app


async def get(app, path, headers=None):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        return await client.get(path, headers=headers or {})


# ---------------------------------------------------------------------------
# RequestIDMiddleware
# ---------------------------------------------------------------------------

class TestRequestIDMiddleware:
    @pytest.mark.anyio
    async def test_adds_x_request_id_header(self):
        app = make_app((RequestIDMiddleware, {}))
        resp = await get(app, "/ping")
        assert "x-request-id" in resp.headers

    @pytest.mark.anyio
    async def test_generated_id_is_not_empty(self):
        app = make_app((RequestIDMiddleware, {}))
        resp = await get(app, "/ping")
        assert len(resp.headers["x-request-id"]) > 0

    @pytest.mark.anyio
    async def test_passes_through_client_request_id(self):
        app = make_app((RequestIDMiddleware, {}))
        resp = await get(app, "/ping", headers={"X-Request-ID": "my-id-123"})
        assert resp.headers["x-request-id"] == "my-id-123"

    @pytest.mark.anyio
    async def test_generates_unique_ids(self):
        app = make_app((RequestIDMiddleware, {}))
        r1 = await get(app, "/ping")
        r2 = await get(app, "/ping")
        assert r1.headers["x-request-id"] != r2.headers["x-request-id"]


# ---------------------------------------------------------------------------
# RateLimitMiddleware
# ---------------------------------------------------------------------------

class TestRateLimitMiddleware:
    @pytest.mark.anyio
    async def test_allows_requests_under_limit(self):
        app = make_app((RateLimitMiddleware, {"requests_per_minute": 5}))
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            for _ in range(5):
                resp = await client.get("/ping")
                assert resp.status_code == 200

    @pytest.mark.anyio
    async def test_blocks_request_over_limit(self):
        app = make_app((RateLimitMiddleware, {"requests_per_minute": 3}))
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            for _ in range(3):
                await client.get("/ping")
            resp = await client.get("/ping")
        assert resp.status_code == 429

    @pytest.mark.anyio
    async def test_429_has_error_body(self):
        app = make_app((RateLimitMiddleware, {"requests_per_minute": 1}))
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            await client.get("/ping")
            resp = await client.get("/ping")
        assert resp.status_code == 429
        body = resp.json()
        assert body["success"] is False
        assert body["error"]["code"] == "RATE_LIMITED"

    @pytest.mark.anyio
    async def test_429_has_retry_after_header(self):
        app = make_app((RateLimitMiddleware, {"requests_per_minute": 1}))
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            await client.get("/ping")
            resp = await client.get("/ping")
        assert "retry-after" in resp.headers

    @pytest.mark.anyio
    async def test_different_ips_tracked_separately(self):
        app = make_app((RateLimitMiddleware, {"requests_per_minute": 2}))
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            for _ in range(2):
                await client.get("/ping", headers={"X-Forwarded-For": "1.2.3.4"})
            resp_a = await client.get("/ping", headers={"X-Forwarded-For": "1.2.3.4"})
            resp_b = await client.get("/ping", headers={"X-Forwarded-For": "5.6.7.8"})
        assert resp_a.status_code == 429
        assert resp_b.status_code == 200


# ---------------------------------------------------------------------------
# LoggingMiddleware
# ---------------------------------------------------------------------------

class TestLoggingMiddleware:
    @pytest.mark.anyio
    async def test_does_not_break_response(self):
        app = make_app((LoggingMiddleware, {}))
        resp = await get(app, "/ping")
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}

    @pytest.mark.anyio
    async def test_logs_request(self, caplog):
        import logging
        app = make_app((LoggingMiddleware, {}))
        with caplog.at_level(logging.INFO, logger="forgeapi.access"):
            await get(app, "/ping")
        assert any("GET" in r.message and "/ping" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# Base Middleware
# ---------------------------------------------------------------------------

class TestBaseMiddleware:
    @pytest.mark.anyio
    async def test_passthrough_by_default(self):
        class NoopMiddleware(Middleware):
            pass

        app = make_app((NoopMiddleware, {}))
        resp = await get(app, "/ping")
        assert resp.status_code == 200

    @pytest.mark.anyio
    async def test_custom_dispatch_modifies_response(self):
        from fastapi import Request, Response
        from typing import Callable

        class HeaderMiddleware(Middleware):
            async def dispatch(self, request: Request, call_next: Callable) -> Response:
                response = await call_next(request)
                response.headers["X-Custom"] = "injected"
                return response

        app = make_app((HeaderMiddleware, {}))
        resp = await get(app, "/ping")
        assert resp.headers["x-custom"] == "injected"
