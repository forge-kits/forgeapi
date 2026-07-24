from __future__ import annotations

import logging
import time
from typing import Any

from ..context import get_current
from ..store import BroadcastRecord

logger = logging.getLogger("forgeapi.telescope")
_INSTALLED = False


def _make_emit_wrapper(orig: Any) -> Any:
    async def wrapper(self: Any, channel: str, data: Any) -> None:
        entry = get_current()
        if entry is None:
            return await orig(self, channel, data)
        t = time.perf_counter()
        try:
            result = await orig(self, channel, data)
        finally:
            entry.broadcasts.append(BroadcastRecord(
                channel=channel,
                payload=data,
                duration_ms=round((time.perf_counter() - t) * 1000, 3),
            ))
        return result
    return wrapper


def install_broadcast_hook() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    try:
        from forgeapi.broadcasting.manager import BroadcastManager
    except ImportError:
        logger.debug("Telescope: BroadcastManager not available — broadcast hook skipped")
        return
    BroadcastManager.emit = _make_emit_wrapper(BroadcastManager.emit)
    _INSTALLED = True
    logger.debug("Telescope: broadcast hook installed")
