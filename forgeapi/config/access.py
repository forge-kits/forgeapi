from __future__ import annotations

from typing import Any

from .loader import load_config
from .models import KitConfig

_current: KitConfig | None = None


def config(key: str | None = None, default: Any = None) -> Any:
    """A value of the project config by its dotted path, from anywhere in the code.

    ::

        from forgeapi.config import config

        config("services.stripe.key")            # a custom section of config/app.py
        config("services.stripe.key", "")        # with a default for a missing key
        config("name")                           # project settings sit at the top level
        config("auth.guards.api.strategy")       # built-in sections work the same way
        config()                                 # the whole KitConfig

    The config is read once and kept: ``Core(app)`` hands over the one it loaded, and without
    ``Core`` (a script, a worker) the first call reads ``config/``.  ``config.clear()`` forgets
    it, so the next call reads ``config/`` again (use it in tests).
    """
    global _current
    if _current is None:
        _current = load_config()
    if key is None:
        return _current
    return _current.get(key, default)


def _use(cfg: KitConfig) -> None:
    """Make *cfg* the config ``config()`` answers from (called by ``Core``)."""
    global _current
    _current = cfg


def _clear() -> None:
    global _current
    _current = None


config.clear = _clear  # type: ignore[attr-defined]
