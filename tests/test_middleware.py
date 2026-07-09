import pytest
import httpx
from fastapi import FastAPI

from forgeapi.middleware.request_id import RequestIDMiddleware
from forgeapi.middleware.rate_limit import RateLimitMiddleware
from forgeapi.middleware.logging import LoggingMiddleware
from forgeapi.middleware.security_headers import SecurityHeadersMiddleware
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
        # trusted_proxies=1 enables X-Forwarded-For-based key extraction
        app = make_app((RateLimitMiddleware, {"requests_per_minute": 2, "trusted_proxies": 1}))
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            for _ in range(2):
                await client.get("/ping", headers={"X-Forwarded-For": "1.2.3.4"})
            resp_a = await client.get("/ping", headers={"X-Forwarded-For": "1.2.3.4"})
            resp_b = await client.get("/ping", headers={"X-Forwarded-For": "5.6.7.8"})
        assert resp_a.status_code == 429
        assert resp_b.status_code == 200

    @pytest.mark.anyio
    async def test_exclude_paths_bypass_rate_limit(self):
        app = make_app((RateLimitMiddleware, {"requests_per_minute": 1, "exclude_paths": ["/ping"]}))
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            for _ in range(5):
                resp = await client.get("/ping")
                assert resp.status_code == 200


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
        matching = [r for r in caplog.records if "GET" in r.message and "/ping" in r.message]
        assert matching, "No access log record found for GET /ping"
        msg = matching[0].message
        assert "200" in msg, f"Status code not in log message: {msg!r}"
        assert "ms" in msg, f"Duration not in log message: {msg!r}"


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


# ---------------------------------------------------------------------------
# SecurityHeadersMiddleware
# ---------------------------------------------------------------------------

class TestSecurityHeadersMiddleware:
    @pytest.mark.anyio
    async def test_adds_security_headers(self):
        app = make_app((SecurityHeadersMiddleware, {}))
        resp = await get(app, "/ping")
        assert resp.headers.get("x-content-type-options") == "nosniff"
        assert resp.headers.get("x-frame-options") == "DENY"
        assert resp.headers.get("referrer-policy") == "strict-origin-when-cross-origin"
        assert "content-security-policy" in resp.headers

    @pytest.mark.anyio
    async def test_custom_csp(self):
        app = make_app((SecurityHeadersMiddleware, {"csp": "default-src 'none'"}))
        resp = await get(app, "/ping")
        assert resp.headers.get("content-security-policy") == "default-src 'none'"

    @pytest.mark.anyio
    async def test_no_csp_when_none(self):
        app = make_app((SecurityHeadersMiddleware, {"csp": None}))
        resp = await get(app, "/ping")
        assert "content-security-policy" not in resp.headers


# ---------------------------------------------------------------------------
# RequestIDMiddleware — sanitisation
# ---------------------------------------------------------------------------

class TestRequestIDSanitisation:
    @pytest.mark.anyio
    async def test_rejects_crlf_injection(self):
        app = make_app((RequestIDMiddleware, {}))
        resp = await get(app, "/ping", headers={"X-Request-ID": "bad\r\nX-Injected: hdr"})
        # Value must be replaced with a safe generated ID, not echoed back
        assert "\r" not in resp.headers.get("x-request-id", "")
        assert "\n" not in resp.headers.get("x-request-id", "")

    @pytest.mark.anyio
    async def test_rejects_oversized_id(self):
        app = make_app((RequestIDMiddleware, {}))
        long_id = "a" * 65
        resp = await get(app, "/ping", headers={"X-Request-ID": long_id})
        assert resp.headers["x-request-id"] != long_id


# ---------------------------------------------------------------------------
# add_cors — security validation
# ---------------------------------------------------------------------------

class TestAddCors:
    def test_credentials_with_wildcard_raises(self):
        import pytest
        from fastapi import FastAPI
        from forgeapi.middleware.cors import add_cors

        app = FastAPI()
        with pytest.raises(ValueError, match="incompatible with wildcard"):
            add_cors(app, allow_credentials=True)

    def test_credentials_with_explicit_origins_ok(self):
        from fastapi import FastAPI
        from forgeapi.middleware.cors import add_cors

        app = FastAPI()
        add_cors(app, origins=["https://example.com"], allow_credentials=True)

    @pytest.mark.anyio
    async def test_add_cors_adds_allow_origin_header(self):
        from fastapi import FastAPI
        from forgeapi.middleware.cors import add_cors

        app = FastAPI()
        add_cors(app, origins=["https://example.com"])

        @app.get("/ping")
        async def ping():
            return {}

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.options(
                "/ping",
                headers={
                    "Origin": "https://example.com",
                    "Access-Control-Request-Method": "GET",
                },
            )
        assert resp.status_code in (200, 204)
        assert "access-control-allow-origin" in resp.headers


# ---------------------------------------------------------------------------
# RateLimitMiddleware — edge cases
# ---------------------------------------------------------------------------

class TestRateLimitEdgeCases:
    @pytest.mark.anyio
    async def test_rpm_zero_blocks_first_request(self):
        app = make_app((RateLimitMiddleware, {"requests_per_minute": 0}))
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/ping")
        assert resp.status_code == 429


# ---------------------------------------------------------------------------
# Guard middleware
# ---------------------------------------------------------------------------

class TestGuardMiddleware:
    def test_call_signature_mirrors_handle(self):
        import inspect
        from fastapi import Request
        from forgeapi.middleware.guard import Guard

        class MyGuard(Guard):
            async def handle(self, request: Request) -> None:
                pass

        sig = inspect.signature(MyGuard.__call__)
        assert "request" in sig.parameters
        assert "self" not in sig.parameters

    @pytest.mark.anyio
    async def test_guard_raises_http_exception(self):
        from fastapi import FastAPI, HTTPException, Depends
        from forgeapi.middleware.guard import Guard

        class BlockGuard(Guard):
            async def handle(self) -> None:
                raise HTTPException(status_code=403, detail="forbidden")

        app = FastAPI()

        @app.get("/secret", dependencies=[Depends(BlockGuard())])
        async def secret():
            return {"ok": True}

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/secret")
        assert resp.status_code == 403

    @pytest.mark.anyio
    async def test_guard_passthrough_allows_request(self):
        from fastapi import FastAPI, Depends
        from forgeapi.middleware.guard import Guard

        class PassGuard(Guard):
            async def handle(self) -> None:
                pass

        app = FastAPI()

        @app.get("/open", dependencies=[Depends(PassGuard())])
        async def open_route():
            return {"ok": True}

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/open")
        assert resp.status_code == 200
