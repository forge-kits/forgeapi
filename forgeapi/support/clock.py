from __future__ import annotations

from datetime import datetime


def config_timezone() -> str | None:
    """``timezone`` from ``config/project.py``, or ``None`` (also when config is unreadable)."""
    try:
        from forgeapi.config import load_config

        return load_config().project.timezone
    except Exception:
        return None


def wall_clock_now(tz: str | None = None) -> datetime:
    """Current time in IANA timezone ``tz`` as a naive datetime (server local time when ``tz`` is None).

    Scheduler and queue store naive wall-clock values, so every component must
    read "now" through this function to stay consistent.
    """
    if tz:
        import zoneinfo

        return datetime.now(zoneinfo.ZoneInfo(tz)).replace(tzinfo=None)
    return datetime.now()


def naive_wall(value: datetime) -> datetime:
    """Normalize a datetime read from a ``DatetimeField`` back to naive wall-clock.

    Scheduler/queue write naive wall-clock values. With Tortoise ``use_tz=True``
    (its default) a naive value is stored as UTC and read back aware, so the
    inverse is "convert to UTC, drop tzinfo". With ``use_tz=False`` it is a no-op.
    """
    if value.tzinfo is None:
        return value
    from datetime import timezone

    return value.astimezone(timezone.utc).replace(tzinfo=None)


def to_db(value: datetime) -> datetime:
    """Prepare a naive wall-clock datetime for a ``DatetimeField`` write or filter.

    With Tortoise ``use_tz=True`` a naive value triggers a RuntimeWarning and is
    treated as UTC anyway, so label it UTC explicitly. ``use_tz=False``: unchanged.
    Inverse of :func:`naive_wall`.
    """
    from datetime import timezone

    from tortoise.timezone import get_use_tz

    if get_use_tz() and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value
