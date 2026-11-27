from __future__ import annotations

from contextvars import ContextVar
from typing import Optional

from starlette.datastructures import MutableHeaders
from starlette.requests import Request
from starlette.responses import Response

from forgeapi.exceptions import ForgeAPIConfigError

from .contracts import SessionCookie


class _RequestState:
    """What one request has to tell the browser: the cookies that ``login()`` and ``logout()`` queued."""

    __slots__ = ("request", "cookies")

    def __init__(self, request: Request) -> None:
        self.request = request
        self.cookies: dict[str, SessionCookie] = {}

    def queue(self, cookie: SessionCookie) -> None:
        self.cookies[cookie.name] = cookie   # the last one for a name wins


_state: ContextVar[Optional[_RequestState]] = ContextVar("_auth_request_state", default=None)


def current_state() -> _RequestState:
    state = _state.get()
    if state is None:
        raise ForgeAPIConfigError(
            "auth.login() and auth.logout() work inside a request, and need AuthMiddleware.",
            hint="Boot the app with Core(app) and a config/auth.py, or add AuthMiddleware yourself.",
        )
    return state


def _header(cookie: SessionCookie) -> str:
    response = Response()
    options = dict(path=cookie.path, httponly=cookie.httponly, secure=cookie.secure, samesite=cookie.samesite)
    if cookie.value is None:
        response.delete_cookie(cookie.name, **options)
    else:
        response.set_cookie(cookie.name, cookie.value, max_age=cookie.max_age, **options)
    return response.headers["set-cookie"]


class AuthMiddleware:
    """Pure ASGI middleware that lets ``auth.login(user)`` and ``auth.logout()`` work without a ``response``.

    It remembers the request for the length of the call and adds the queued
    ``Set-Cookie`` headers when the response starts.
    """

    __slots__ = ("app",)

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        state = _RequestState(Request(scope, receive))
        token = _state.set(state)

        async def send_with_cookies(message) -> None:
            if message["type"] == "http.response.start" and state.cookies:
                headers = MutableHeaders(scope=message)
                for cookie in state.cookies.values():
                    headers.append("set-cookie", _header(cookie))
            await send(message)

        try:
            await self.app(scope, receive, send_with_cookies)
        finally:
            _state.reset(token)
