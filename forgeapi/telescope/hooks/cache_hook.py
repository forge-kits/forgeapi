from __future__ import annotations

import logging
import time
from typing import Any

from ..context import get_current
from ..store import CacheRecord

logger = logging.getLogger("forgeapi.telescope")
_INSTALLED = False


def _make_get_wrapper(orig: Any) -> Any:
    async def wrapper(self: Any, key: str, default: Any = None) -> Any:
        entry = get_current()
        if entry is None:
            return await orig(self, key, default)
        t = time.perf_counter()
        result = await orig(self, key, default)
        entry.caches.append(CacheRecord(
            op="get",
            key=key,
            hit=result is not default,
            duration_ms=round((time.perf_counter() - t) * 1000, 3),
        ))
        return result
    return wrapper


def _make_set_wrapper(orig: Any, sentinel: Any) -> Any:
    async def wrapper(self: Any, key: str, value: Any, ttl: Any = sentinel) -> None:
        entry = get_current()
        if entry is None:
            return await orig(self, key, value, ttl)
        t = time.perf_counter()
        try:
            result = await orig(self, key, value, ttl)
        finally:
            entry.caches.append(CacheRecord(
                op="set",
                key=key,
                hit=None,
                duration_ms=round((time.perf_counter() - t) * 1000, 3),
            ))
        return result
    return wrapper


def _make_forget_wrapper(orig: Any) -> Any:
    async def wrapper(self: Any, key: str) -> bool:
        entry = get_current()
        if entry is None:
            return await orig(self, key)
        t = time.perf_counter()
        try:
            result = await orig(self, key)
        finally:
            entry.caches.append(CacheRecord(
                op="forget",
                key=key,
                hit=None,
                duration_ms=round((time.perf_counter() - t) * 1000, 3),
            ))
        return result
    return wrapper


def install_cache_hook() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    try:
        from forgeapi.cache.cache import _Cache, _SENTINEL
    except ImportError:
        logger.debug("Telescope: Cache not available — cache hook skipped")
        return
    _Cache.get = _make_get_wrapper(_Cache.get)
    _Cache.set = _make_set_wrapper(_Cache.set, _SENTINEL)
    _Cache.put = _make_set_wrapper(_Cache.put, _SENTINEL)
    _Cache.forget = _make_forget_wrapper(_Cache.forget)
    _INSTALLED = True
    logger.debug("Telescope: cache hook installed")
