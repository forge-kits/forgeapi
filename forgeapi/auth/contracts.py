"""Capability contracts for auth strategies.

A strategy declares what it can do by implementing these protocols —
:class:`~forgeapi.auth.guard.Guard` and the :class:`~forgeapi.auth.facade.Auth`
facade dispatch on the protocol, never on a concrete strategy class.
A custom strategy that implements a protocol gets the matching facade
methods for free.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

__all__ = ["TokenIssuer", "RefreshCapable", "SessionIssuer"]


@runtime_checkable
class TokenIssuer(Protocol):
    """Strategy that can issue and verify stateless tokens (e.g. JWT)."""

    def create_access_token(self, payload: dict) -> str: ...

    def decode(self, token: str, *, expected_type: str | None = None) -> dict: ...


@runtime_checkable
class RefreshCapable(Protocol):
    """Strategy that supports long-lived refresh tokens."""

    def create_refresh_token(self, payload: dict) -> str: ...


@runtime_checkable
class SessionIssuer(Protocol):
    """Strategy that manages signed sessions delivered via cookies."""

    def create_session(self, data: dict) -> str: ...

    def set_cookie(self, response, data: dict) -> None: ...

    def delete_cookie(self, response) -> None: ...
