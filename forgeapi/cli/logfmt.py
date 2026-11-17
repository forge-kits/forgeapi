"""Recognise the level of a log line from any forgeapi process and show all of them alike.

Three sources print differently: uvicorn (``INFO:     message``), forgeapi CLI commands
(``   INFO   message`` badges) and the forgeapi logger (``2026-11-17 16:36:06  INFO  forgeapi.x  message``).
"""
from __future__ import annotations

import re
from typing import NamedTuple

from rich.text import Text

#: Shown level -> style.
LEVEL_STYLES = {
    "DEBUG": "dim",
    "INFO": "cyan",
    "DONE": "green",
    "WARNING": "yellow",
    "ERROR": "bold red",
    "CRITICAL": "bold red",
}
LEVEL_WIDTH = max(len(name) for name in LEVEL_STYLES)

_ALIASES = {"WARN": "WARNING", "OK": "DONE", "FAIL": "ERROR"}
_LEVEL = r"DEBUG|INFO|WARNING|WARN|ERROR|CRITICAL|DONE|OK|FAIL"

# uvicorn:        INFO:     Application startup complete.
_UVICORN = re.compile(rf"^({_LEVEL}):\s+")
# forgeapi CLI:      INFO   Queue worker started          (a badge: text between spaces, then 2+ spaces)
_BADGE = re.compile(rf"^\s*({_LEVEL})\s{{2,}}")
# forgeapi logger:  2026-11-17 16:36:06  INFO  forgeapi.cache.provider  Cache: driver=database
_LOGGER = re.compile(rf"^\d{{4}}-\d\d-\d\d \d\d:\d\d:\d\d\s+({_LEVEL})\s+(\S+)\s+")


class Parsed(NamedTuple):
    level: str | None       # None: the line has no recognisable level
    message: Text           # keeps the colours of the original line
    logger: str | None      # name of the forgeapi/app logger that wrote it, when the line says so


def parse_line(text: Text) -> Parsed:
    """Level, message and logger of one output line.

    ``text`` keeps its colours (``Text.from_ansi``): the message is a slice of it, not a rebuild.
    """
    plain = text.plain
    for pattern in (_UVICORN, _LOGGER, _BADGE):
        match = pattern.match(plain)
        if match:
            level = _ALIASES.get(match.group(1), match.group(1))
            message = text[match.end():]
            logger = None
            if pattern is _LOGGER:
                logger = match.group(2)
                message = Text.assemble((logger, "dim"), "  ", message)
            return Parsed(level, message, logger)
    return Parsed(None, text, None)
