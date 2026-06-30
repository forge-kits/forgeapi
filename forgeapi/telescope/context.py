from __future__ import annotations

from contextvars import ContextVar
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .store import RequestEntry

_current: ContextVar["RequestEntry | None"] = ContextVar("_debug_entry", default=None)


def set_current(entry: "RequestEntry") -> None:
    _current.set(entry)


def get_current() -> "RequestEntry | None":
    return _current.get()


def clear_current() -> None:
    _current.set(None)
