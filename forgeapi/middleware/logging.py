import logging
import time

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

logger = logging.getLogger("forgeapi.access")


class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        start = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            return response
        finally:
            duration_ms = (time.perf_counter() - start) * 1000
            request_id = getattr(request.state, "request_id", "-")
            logger.info(
                "%s %s → %d [%.1fms] req_id=%s",
                request.method,
                request.url.path,
                status,
                duration_ms,
                request_id,
            )
