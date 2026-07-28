from forgeapi.http.context import _current_request, set_request


class RequestContextMiddleware:
    """Pure ASGI middleware — stores the current Request in a ContextVar.

    Allows queryset pagination methods to access the request (for reading
    ``?page``/``?per_page``/``?cursor`` and building prev/next links) without
    requiring it to be passed explicitly through every call stack.
    """

    __slots__ = ("app",)

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] == "http":
            from starlette.requests import Request
            token = set_request(Request(scope, receive))
            try:
                await self.app(scope, receive, send)
            finally:
                _current_request.reset(token)
            return
        await self.app(scope, receive, send)
