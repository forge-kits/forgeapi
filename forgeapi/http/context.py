from contextvars import ContextVar, Token
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from starlette.requests import Request

_current_request: ContextVar["Request | None"] = ContextVar("_current_request", default=None)


def set_request(request: "Request") -> Token:
    return _current_request.set(request)


def get_request() -> "Request | None":
    return _current_request.get()
