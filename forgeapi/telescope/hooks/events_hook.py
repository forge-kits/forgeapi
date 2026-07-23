from __future__ import annotations

import logging

logger = logging.getLogger("forgeapi.telescope")


def install_events_hook() -> None:
    # EventBus removed — BroadcastManager telemetry to be implemented
    logger.debug("Telescope: events hook skipped (BroadcastManager not yet instrumented)")
