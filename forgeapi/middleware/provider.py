from __future__ import annotations

from forgeapi.foundation import Provider
from forgeapi.logging import log

_log = log.channel("middleware.provider")


class MiddlewareProvider(Provider):
    """Registers the global middleware stack from the ``http`` config section.

    Starlette prepends on ``add_middleware``, so the LAST added middleware is
    the outermost.  Registration order (inner → outer): custom middleware,
    access log, request ID, CORS, rate limit.  Do not reorder — it changes
    the runtime stack.
    """

    def register(self) -> None:
        http = self.config.http

        for item in http.middleware:
            if isinstance(item, tuple):
                cls, kwargs = item
                self.app.add_middleware(cls, **kwargs)
            else:
                self.app.add_middleware(item)

        if http.access_log:
            from .logging import LoggingMiddleware
            self.app.add_middleware(LoggingMiddleware)
            _log.debug("Middleware: access logging enabled")
        if http.request_id:
            from .request_id import RequestIDMiddleware
            self.app.add_middleware(RequestIDMiddleware)
            _log.debug("Middleware: request ID injection enabled")
        if http.cors is not False:
            from .cors import add_cors
            origins = http.cors if isinstance(http.cors, list) else ["*"]
            add_cors(self.app, origins=origins)
            _log.debug("Middleware: CORS enabled, origins=%s", origins)
        if http.rate_limit is not False:
            from .rate_limit import RateLimitMiddleware
            rpm = http.rate_limit if not isinstance(http.rate_limit, bool) else 60
            self.app.add_middleware(RateLimitMiddleware, requests_per_minute=rpm)
            _log.debug("Middleware: rate limit %d req/min", rpm)
