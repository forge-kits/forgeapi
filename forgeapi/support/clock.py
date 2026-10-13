from __future__ import annotations

from datetime import datetime


def config_queue_retry_after() -> int:
    """``queue.retry_after`` from ``config/queue.py`` (300 when unset or config unreadable)."""
    try:
        from forgeapi.config import load_config

        return load_config().queue.retry_after
    except Exception:
        return 300


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


def _timestamptz_backend() -> bool:
    """True when the default connection stores datetimes as timestamptz (PostgreSQL)."""
    try:
        from tortoise import connections

        return connections.get("default").capabilities.dialect == "postgres"
    except Exception:
        return False


def to_db(value: datetime) -> datetime:
    """Prepare a naive wall-clock datetime for a ``DatetimeField`` write or filter.

    The wall-clock value is labeled UTC (the label is only a carrier, see
    :func:`naive_wall`) when Tortoise ``use_tz=True`` (a naive value would warn
    and be treated as UTC anyway) or when the backend stores ``timestamptz``
    (PostgreSQL): the driver interprets a naive value in the *host's* timezone,
    which shifts the stored time by the host's UTC offset. Otherwise unchanged.
    """
    from datetime import timezone

    from tortoise.timezone import get_use_tz

    if value.tzinfo is None and (get_use_tz() or _timestamptz_backend()):
        return value.replace(tzinfo=timezone.utc)
    return value
