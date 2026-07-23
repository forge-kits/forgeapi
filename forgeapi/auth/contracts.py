"""Capability contracts for auth strategies."""
from __future__ import annotations
from typing import Protocol, runtime_checkable

__all__ = ["SessionIssuer"]


@runtime_checkable
class SessionIssuer(Protocol):
    """Strategy that manages signed sessions delivered via cookies."""

    def create_session(self, data: dict) -> str: ...

    def set_cookie(self, response, data: dict) -> None: ...

    def delete_cookie(self, response) -> None: ...
