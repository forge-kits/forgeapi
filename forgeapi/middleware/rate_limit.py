import logging
import time
from collections import defaultdict, deque

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

logger = logging.getLogger("forgeapi.rate_limit")


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, requests_per_minute: int = 60) -> None:
        super().__init__(app)
        self._rpm = requests_per_minute
        self._window = 60.0
        self._store: dict[str, deque] = defaultdict(deque)

    async def dispatch(self, request: Request, call_next) -> Response:
        client_ip = (
            request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
            or request.headers.get("X-Real-IP", "")
            or (request.client.host if request.client else "unknown")
        )
        now = time.time()
        window_start = now - self._window

        timestamps = self._store[client_ip]
        while timestamps and timestamps[0] < window_start:
            timestamps.popleft()
        if not timestamps and client_ip in self._store:
            del self._store[client_ip]
            timestamps = self._store[client_ip]

        if len(timestamps) >= self._rpm:
            logger.warning("Rate limit exceeded: ip=%s requests=%d limit=%d", client_ip, len(timestamps), self._rpm)
            return JSONResponse(
                status_code=429,
                content={
                    "success": False,
                    "error": {"code": "RATE_LIMITED", "message": "Too many requests. Slow down."},
                },
                headers={"Retry-After": str(int(self._window))},
            )

        timestamps.append(now)
        return await call_next(request)
