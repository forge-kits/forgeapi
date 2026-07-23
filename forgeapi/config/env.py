import os
from typing import Any

__all__ = ["env"]


def env(key: str, default: Any = None) -> Any:
    """Read an environment variable — Laravel ``env()`` equivalent.

    Casts the literal strings ``"true"`` / ``"false"`` / ``"null"`` (any case)
    to ``True`` / ``False`` / ``None``.  Everything else is returned as a
    string; numeric fields are coerced later by config validation.

    Use inside ``config/*.py`` files::

        from forgeapi import env

        config = {
            "guards": {
                "api": {"strategy": "cookie", "secret": env("COOKIE_SECRET")},
            },
        }

    Args:
        key:     Environment variable name.
        default: Returned when the variable is not set.
    """
    value = os.getenv(key)
    if value is None:
        return default
    lowered = value.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if lowered == "null":
        return None
    return value
