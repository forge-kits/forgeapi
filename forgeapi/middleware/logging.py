import logging
import time

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

logger = logging.getLogger("forgeapi.access")


class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        start = time.perf_counter()
        status: int | None = None
        try:
            response = await call_next(request)
            status = response.status_code
        except Exception as exc:
            duration_ms = (time.perf_counter() - start) * 1000
            request_id = getattr(request.state, "request_id", "-")
            logger.error(
                "%s %s → ERROR [%.1fms] req_id=%s",
                request.method,
                request.url.path,
                duration_ms,
                request_id,
                exc_info=exc,
            )
            raise
        else:
            duration_ms = (time.perf_counter() - start) * 1000
            request_id = getattr(request.state, "request_id", "-")
            log = (
                logger.error
                if status >= 500
                else logger.warning
                if status >= 400
                else logger.info
            )
            log(
                "%s %s → %d [%.1fms] req_id=%s",
                request.method,
                request.url.path,
                status,
                duration_ms,
                request_id,
            )
            return response
