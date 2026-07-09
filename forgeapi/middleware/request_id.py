import re
import uuid

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

# Only accept request IDs that contain safe characters and fit within a
# reasonable length.  CRLF and other control characters are rejected to
# prevent HTTP response header splitting.
_REQUEST_ID_RE = re.compile(r"[a-zA-Z0-9_-]{1,64}")


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        raw_id = request.headers.get("X-Request-ID", "")
        if raw_id and _REQUEST_ID_RE.fullmatch(raw_id):
            request_id = raw_id
        else:
            request_id = uuid.uuid4().hex
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response
