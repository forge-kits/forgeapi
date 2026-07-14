from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Union
import re

DateTimeInput = Union[datetime, str, int, float]


def _parse(value: DateTimeInput) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc)
    if isinstance(value, str):
        for fmt in (
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d",
        ):
            try:
                return datetime.strptime(value, fmt)
            except ValueError:
                continue
        raise ValueError(f"Cannot parse date: {value!r}")
    raise TypeError(f"Expected datetime, str, int or float, got {type(value)}")


class Time:
    @staticmethod
    def now(tz: str | None = None) -> datetime:
        """Current UTC datetime (or in given IANA timezone)."""
        import zoneinfo
        if tz:
            return datetime.now(zoneinfo.ZoneInfo(tz))
        return datetime.now(timezone.utc)

    @staticmethod
    def parse(value: DateTimeInput) -> datetime:
        """Parse a datetime from string, timestamp, or datetime object."""
        return _parse(value)

    @staticmethod
    def format(value: DateTimeInput, fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
        """Format a datetime to a string.

        Time.format(dt)                        → '2025-07-14 12:00:00'
        Time.format(dt, '%d/%m/%Y')            → '14/07/2025'
        """
        return _parse(value).strftime(fmt)

    @staticmethod
    def to_timezone(value: DateTimeInput, tz: str) -> datetime:
        """Convert a datetime to a different timezone.

        Time.to_timezone(dt, 'Europe/Kyiv')
        """
        import zoneinfo
        dt = _parse(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(zoneinfo.ZoneInfo(tz))

    @staticmethod
    def timestamp(value: DateTimeInput) -> int:
        """Return Unix timestamp as int."""
        dt = _parse(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp())

    @staticmethod
    def diff_in_seconds(a: DateTimeInput, b: DateTimeInput) -> int:
        """Absolute difference between two datetimes in seconds."""
        da, db = _parse(a), _parse(b)
        return int(abs((da - db).total_seconds()))

    @staticmethod
    def diff_in_days(a: DateTimeInput, b: DateTimeInput) -> int:
        """Absolute difference in days."""
        da, db = _parse(a), _parse(b)
        return abs((da - db).days)

    @staticmethod
    def add(value: DateTimeInput, **kwargs) -> datetime:
        """Add time to a datetime.

        Time.add(dt, days=1, hours=3)
        """
        return _parse(value) + timedelta(**kwargs)

    @staticmethod
    def subtract(value: DateTimeInput, **kwargs) -> datetime:
        """Subtract time from a datetime.

        Time.subtract(dt, days=7)
        """
        return _parse(value) - timedelta(**kwargs)

    @staticmethod
    def human(value: DateTimeInput, relative_to: DateTimeInput | None = None) -> str:
        """Human-readable relative time.

        Time.human(dt)  → 'just now' / '5 minutes ago' / 'in 3 hours'
        """
        dt = _parse(value)
        base = _parse(relative_to) if relative_to else datetime.now(timezone.utc)

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        if base.tzinfo is None:
            base = base.replace(tzinfo=timezone.utc)

        delta = (dt - base).total_seconds()
        past = delta < 0
        seconds = abs(int(delta))

        thresholds = [
            (45,       "just now"),
            (90,       "a minute ago" if past else "in a minute"),
            (2700,     f"{seconds // 60} minutes ago" if past else f"in {seconds // 60} minutes"),
            (5400,     "an hour ago" if past else "in an hour"),
            (79200,    f"{seconds // 3600} hours ago" if past else f"in {seconds // 3600} hours"),
            (129600,   "yesterday" if past else "tomorrow"),
            (2160000,  f"{seconds // 86400} days ago" if past else f"in {seconds // 86400} days"),
            (3888000,  "a month ago" if past else "in a month"),
            (31536000, f"{seconds // 2592000} months ago" if past else f"in {seconds // 2592000} months"),
        ]

        for limit, label in thresholds:
            if seconds <= limit:
                return label

        years = seconds // 31536000
        return f"{years} year{'s' if years != 1 else ''} ago" if past else f"in {years} year{'s' if years != 1 else ''}"

    @staticmethod
    def is_past(value: DateTimeInput) -> bool:
        dt = _parse(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt < datetime.now(timezone.utc)

    @staticmethod
    def is_future(value: DateTimeInput) -> bool:
        return not Time.is_past(value)

    @staticmethod
    def start_of_day(value: DateTimeInput) -> datetime:
        dt = _parse(value)
        return dt.replace(hour=0, minute=0, second=0, microsecond=0)

    @staticmethod
    def end_of_day(value: DateTimeInput) -> datetime:
        dt = _parse(value)
        return dt.replace(hour=23, minute=59, second=59, microsecond=999999)
