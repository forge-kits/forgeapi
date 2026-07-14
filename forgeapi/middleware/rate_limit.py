import time
from collections import defaultdict, deque

from fastapi import Request
from forgeapi.logging import log
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

_log = log.channel("rate_limit")


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Sliding-window in-memory rate limiter keyed by client IP.

    .. warning::
        This is an **in-memory** store — it is **not** shared across multiple
        processes or workers.  For multi-process deployments (e.g. Gunicorn
        with several workers) use a Redis-backed implementation instead.

    Args:
        requests_per_minute: Maximum requests allowed per IP per 60-second
            sliding window.
        trusted_proxies: Number of trusted reverse-proxy hops in front of this
            application.  When > 0 the rate-limit key is taken from the
            ``X-Forwarded-For`` header (Nth entry from the right, where N is
            *trusted_proxies*), which allows correct identification behind a
            load balancer.  When 0 (default) ``request.client.host`` is always
            used — clients cannot spoof their IP via headers.
        exclude_paths: URL path prefixes that bypass rate limiting entirely.
            Defaults to ``["/health", "/healthz", "/readyz", "/metrics"]`` so
            Kubernetes liveness/readiness probes never consume quota.
    """

    def __init__(
        self,
        app,
        requests_per_minute: int = 60,
        trusted_proxies: int = 0,
        exclude_paths: list[str] | None = None,
    ) -> None:
        super().__init__(app)
        self._rpm = requests_per_minute
        self._window = 60.0
        self._trusted_proxies = trusted_proxies
        self._exclude_paths: list[str] = (
            exclude_paths
            if exclude_paths is not None
            else ["/health", "/healthz", "/readyz", "/metrics"]
        )
        self._store: dict[str, deque[float]] = defaultdict(deque)

    def _client_key(self, request: Request) -> str:
        if self._trusted_proxies > 0:
            xff = request.headers.get("X-Forwarded-For", "")
            if xff:
                parts = [p.strip() for p in xff.split(",")]
                # Read the Nth entry from the right where N = trusted_proxies.
                # Entries added by a trusted proxy from the right are reliable;
                # leftmost entries are client-supplied and untrusted.
                idx = max(0, len(parts) - self._trusted_proxies)
                return parts[idx]
        return request.client.host if request.client else "unknown"

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if any(request.url.path.startswith(p) for p in self._exclude_paths):
            return await call_next(request)

        client_ip = self._client_key(request)
        now = time.time()
        window_start = now - self._window

        timestamps = self._store[client_ip]
        while timestamps and timestamps[0] < window_start:
            timestamps.popleft()

        if len(timestamps) >= self._rpm:
            _log.warning(
                "Rate limit exceeded: ip=%s requests=%d limit=%d",
                client_ip,
                len(timestamps),
                self._rpm,
            )
            return JSONResponse(
                status_code=429,
                content={
                    "success": False,
                    "error": {
                        "code": "RATE_LIMITED",
                        "message": "Too many requests. Slow down.",
                    },
                },
                headers={"Retry-After": str(int(self._window))},
            )

        timestamps.append(now)
        return await call_next(request)
