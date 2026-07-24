"""ForgeAPI Telescope — in-memory request inspector.

Activated automatically when ``Core(app, debug=True)``.

WebSocket endpoint (only in debug mode):
    WS     /_forge/telescope/ws       — live stream; sends init/entry/clear JSON messages
    DELETE /_forge/telescope/requests — clear store
"""

from __future__ import annotations

import logging

from .store import DebugStore

logger = logging.getLogger("forgeapi.telescope")

__all__ = ["setup_telescope", "DebugStore"]


def setup_telescope(app) -> None:
    """Install all Telescope hooks and mount the router on *app*.

    Called automatically by ``Core`` when ``debug=True``.
    Safe to call multiple times — hooks are idempotent.
    """
    from .middleware import DebugMiddleware
    from .hooks.logging_hook import install_logging_hook
    from .hooks.tortoise_hook import install_tortoise_hook
    from .hooks.broadcast_hook import install_broadcast_hook
    from .hooks.cache_hook import install_cache_hook
    from .router import router

    app.add_middleware(DebugMiddleware)
    logger.debug("Telescope: request capture middleware registered")

    install_logging_hook()
    install_tortoise_hook()
    install_broadcast_hook()
    install_cache_hook()

    app.include_router(router)
    logger.debug("Telescope: endpoints mounted at /_forge/telescope/requests")
