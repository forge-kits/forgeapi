from __future__ import annotations

import logging

from ..context import get_current
from ..store import EventRecord

logger = logging.getLogger("forgeapi.telescope")
_INSTALLED = False


def install_events_hook() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    from forgeapi.events.bus import EventBus

    _orig_dispatch = EventBus.dispatch

    async def _patched_dispatch(self: EventBus, event: object) -> None:
        entry = get_current()
        if entry is not None:
            try:
                listeners = self.listeners_for(type(event))
                entry.events.append(EventRecord(
                    event=type(event).__name__,
                    listeners=[fn.__name__ for fn in listeners],
                    background=bool(getattr(event, "background", False)),
                ))
            except Exception:
                logger.debug("Telescope: failed to record event", exc_info=True)
        await _orig_dispatch(self, event)

    EventBus.dispatch = _patched_dispatch  # type: ignore[method-assign]
    _INSTALLED = True
    logger.debug("Telescope: EventBus hook installed")
