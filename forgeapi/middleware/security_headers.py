from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Inject common security response headers on every reply.

    Uses ``setdefault`` so application routes can still override any header
    by setting it explicitly before the response is returned.

    Headers added by default:

    * ``X-Content-Type-Options: nosniff`` — prevents MIME-type sniffing.
    * ``X-Frame-Options: DENY`` — prevents clickjacking via iframes.
    * ``Referrer-Policy: strict-origin-when-cross-origin`` — limits referrer
      leakage to same-origin or HTTPS→HTTPS cross-origin requests.
    * ``Content-Security-Policy: default-src 'self'`` — basic allowlist;
      override *csp* if the application loads resources from other origins.

    Args:
        csp: ``Content-Security-Policy`` header value.  Set to ``None`` to
            skip CSP injection (useful when a custom policy is applied
            elsewhere, e.g. in a CDN or reverse proxy).

    Example::

        from forgeapi.middleware import SecurityHeadersMiddleware

        core = Core(app, middleware=[SecurityHeadersMiddleware])

    Example — custom CSP::

        core.use(
            SecurityHeadersMiddleware,
            csp="default-src 'self'; img-src 'self' data: https://cdn.example.com",
        )
    """

    _DEFAULT_CSP = "default-src 'self'"

    def __init__(self, app, csp: str | None = _DEFAULT_CSP) -> None:
        super().__init__(app)
        self._csp = csp

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        if self._csp is not None:
            response.headers.setdefault("Content-Security-Policy", self._csp)
        return response
