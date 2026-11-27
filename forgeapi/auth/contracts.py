"""Capability contracts for auth strategies."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional, Protocol, runtime_checkable

__all__ = ["SessionCookie", "SessionIssuer"]


@dataclass(frozen=True)
class SessionCookie:
    """A cookie a strategy wants on the response.  ``value=None`` removes it."""

    name: str
    value: Optional[str]
    max_age: int
    httponly: bool = True
    secure: bool = True
    samesite: Literal["lax", "strict", "none"] = "lax"
    path: str = "/"


@runtime_checkable
class SessionIssuer(Protocol):
    """Strategy that keeps login sessions on the server and hands the browser a cookie."""

    async def login(self, request, user_id) -> SessionCookie: ...

    async def logout(self, request) -> SessionCookie: ...

    async def logout_others(self, request, user_id) -> int: ...
