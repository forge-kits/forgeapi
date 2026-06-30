from __future__ import annotations

import logging

from ..context import get_current
from ..store import LogRecord

_INSTALLED = False


class DebugLogHandler(logging.Handler):
    """Captures every log record and appends it to the active request entry."""

    # Loggers that would create infinite recursion or noise
    _SKIP_LOGGERS = frozenset({"forgeapi.telescope", "forgeapi.access"})

    def emit(self, record: logging.LogRecord) -> None:
        if record.name in self._SKIP_LOGGERS:
            return
        entry = get_current()
        if entry is None:
            return
        entry.logs.append(LogRecord(
            level=record.levelname,
            logger=record.name,
            message=self.format(record),
            time=self.formatTime(record),
        ))


def install_logging_hook() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    handler = DebugLogHandler()
    handler.setLevel(logging.DEBUG)
    logging.getLogger().addHandler(handler)
    _INSTALLED = True
