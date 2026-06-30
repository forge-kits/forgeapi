from __future__ import annotations

import logging
import time
import traceback
from typing import Any

from ..context import get_current
from ..store import SqlRecord

logger = logging.getLogger("forgeapi.telescope")
_INSTALLED = False

_SKIP_IN_PATH = (
    "site-packages/",
    ".venv/",
    "/forgeapi/telescope",
    "lib/python",
    "<",
)


def _caller_location() -> str:
    for frame in reversed(traceback.extract_stack()):
        path = frame.filename.replace("\\", "/")
        if not any(skip in path for skip in _SKIP_IN_PATH):
            return f"{frame.filename}:{frame.lineno} in {frame.name}"
    return "unknown"


def _record(sql: str, params: Any, duration_ms: float, location: str) -> None:
    entry = get_current()
    if entry is not None:
        entry.queries.append(SqlRecord(
            sql=sql,
            params=params,
            duration_ms=duration_ms,
            location=location,
        ))


def _make_query_wrapper(orig: Any) -> Any:
    async def wrapper(self: Any, query: str, values: Any = None) -> Any:
        if get_current() is None:
            return await orig(self, query, values)
        loc = _caller_location()
        t = time.perf_counter()
        result = await orig(self, query, values)
        _record(query, values, round((time.perf_counter() - t) * 1000, 3), loc)
        return result
    return wrapper


def _make_insert_wrapper(orig: Any) -> Any:
    async def wrapper(self: Any, query: str, values: Any) -> Any:
        if get_current() is None:
            return await orig(self, query, values)
        loc = _caller_location()
        t = time.perf_counter()
        result = await orig(self, query, values)
        _record(query, values, round((time.perf_counter() - t) * 1000, 3), loc)
        return result
    return wrapper


def _make_many_wrapper(orig: Any) -> Any:
    async def wrapper(self: Any, query: str, values: Any) -> Any:
        if get_current() is None:
            return await orig(self, query, values)
        loc = _caller_location()
        t = time.perf_counter()
        result = await orig(self, query, values)
        _record(query, values, round((time.perf_counter() - t) * 1000, 3), loc)
        return result
    return wrapper


def _make_script_wrapper(orig: Any) -> Any:
    async def wrapper(self: Any, query: str) -> Any:
        if get_current() is None:
            return await orig(self, query)
        loc = _caller_location()
        t = time.perf_counter()
        result = await orig(self, query)
        _record(query, None, round((time.perf_counter() - t) * 1000, 3), loc)
        return result
    return wrapper


_ATTR_WRAPPERS = {
    "execute_query": _make_query_wrapper,
    "execute_insert": _make_insert_wrapper,
    "execute_many": _make_many_wrapper,
    "execute_script": _make_script_wrapper,
}


def _patch_class(cls: type) -> None:
    """Patch execute_* on cls only if cls defines them in its own __dict__."""
    for attr, make_wrapper in _ATTR_WRAPPERS.items():
        if attr in cls.__dict__:
            setattr(cls, attr, make_wrapper(cls.__dict__[attr]))


def _walk_subclasses(cls: type) -> None:
    """Recursively patch all subclasses (skip the base class itself)."""
    for sub in cls.__subclasses__():
        _patch_class(sub)
        _walk_subclasses(sub)


def install_tortoise_hook() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    try:
        from tortoise.backends.base.client import BaseDBAsyncClient
    except ImportError:
        logger.debug("Telescope: Tortoise not available — SQL hook skipped")
        return

    # Patch all already-imported backend subclasses
    _walk_subclasses(BaseDBAsyncClient)

    # Auto-patch backend classes imported after this point (e.g. on Tortoise.init())
    def _new_subclass_hook(cls_: type, **kwargs: Any) -> None:
        _patch_class(cls_)

    BaseDBAsyncClient.__init_subclass__ = classmethod(_new_subclass_hook)  # type: ignore[assignment]

    _INSTALLED = True
    logger.debug("Telescope: Tortoise SQL hook installed")
