from typing import Callable, Awaitable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware


class Middleware(BaseHTTPMiddleware):
    """Base class for custom global middleware.

    Subclass and override :meth:`dispatch` — the standard Starlette middleware
    hook. Register via ``Core(app, middleware=[...])`` or ``core.use()``.

    Example::

        from forgeapi.middleware import Middleware

        class TimingMiddleware(Middleware):
            async def dispatch(self, request: Request, call_next: Callable) -> Response:
                import time
                start = time.perf_counter()
                response = await call_next(request)
                response.headers["X-Process-Time"] = f"{time.perf_counter() - start:.3f}s"
                return response

        core = Core(app, middleware=[TimingMiddleware])

    Example — with constructor arguments::

        class TenantMiddleware(Middleware):
            def __init__(self, app, default_tenant: str = "public"):
                super().__init__(app)
                self.default_tenant = default_tenant

            async def dispatch(self, request: Request, call_next: Callable) -> Response:
                request.state.tenant = request.headers.get("X-Tenant", self.default_tenant)
                return await call_next(request)

        core.use(TenantMiddleware, default_tenant="acme")
    """

    async def dispatch(self, request: Request, call_next: Callable[..., Awaitable[Response]]) -> Response:
        return await call_next(request)
