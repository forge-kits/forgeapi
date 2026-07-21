from __future__ import annotations

import asyncio
import inspect
import logging
from datetime import datetime, timedelta
from typing import Callable

log = logging.getLogger("forgeapi.scheduler")


class ScheduledJob:
    """Builder returned by :meth:`Scheduler.call` — configure the schedule
    by chaining one of the timing methods.

    All timing methods return ``self`` for chaining::

        scheduler.call(send_report).daily_at("09:00").name("daily-report")
    """

    def __init__(self, fn: Callable, label: str) -> None:
        self._fn = fn
        self._label = label
        self._next_run: datetime | None = None
        self._interval: timedelta | None = None
        self._daily_hm: tuple[int, int] | None = None  # (hour, minute)
        self._weekly_dhm: tuple[int, int, int] | None = None  # (weekday 0=Mon, hour, minute)

    # ------------------------------------------------------------------
    # Timing methods
    # ------------------------------------------------------------------

    def name(self, label: str) -> "ScheduledJob":
        """Override the display label (defaults to function name)."""
        self._label = label
        return self

    def every_minute(self) -> "ScheduledJob":
        self._interval = timedelta(minutes=1)
        return self

    def every(self, minutes: int) -> "ScheduledJob":
        """Run every *minutes* minutes."""
        self._interval = timedelta(minutes=minutes)
        return self

    def every_hours(self, hours: int = 1) -> "ScheduledJob":
        self._interval = timedelta(hours=hours)
        return self

    def hourly(self) -> "ScheduledJob":
        return self.every_hours(1)

    def daily(self) -> "ScheduledJob":
        """Run once a day at midnight."""
        return self.daily_at("00:00")

    def daily_at(self, time: str) -> "ScheduledJob":
        """Run once a day at *time* (``"HH:MM"``)."""
        h, m = time.split(":")
        self._daily_hm = (int(h), int(m))
        return self

    def weekly(self) -> "ScheduledJob":
        """Run every Monday at midnight."""
        return self.weekly_on("monday")

    def weekly_on(self, day: str, at: str = "00:00") -> "ScheduledJob":
        """Run once a week on *day* (``"monday"`` … ``"sunday"``) at *at*.

        Example::

            scheduler.call(backup).weekly_on("sunday", at="03:00")
        """
        days = {
            "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
            "friday": 4, "saturday": 5, "sunday": 6,
        }
        idx = days.get(day.lower())
        if idx is None:
            raise ValueError(
                f"Unknown day '{day}'. Use: monday, tuesday, …, sunday."
            )
        h, m = at.split(":")
        self._weekly_dhm = (idx, int(h), int(m))
        return self

    # ------------------------------------------------------------------
    # Internal scheduling logic
    # ------------------------------------------------------------------

    def _compute_first_next_run(self, now: datetime) -> datetime:
        if self._interval:
            return now + self._interval

        if self._daily_hm:
            h, m = self._daily_hm
            candidate = now.replace(hour=h, minute=m, second=0, microsecond=0)
            if candidate <= now:
                candidate += timedelta(days=1)
            return candidate

        if self._weekly_dhm:
            target_wd, h, m = self._weekly_dhm
            days_ahead = (target_wd - now.weekday()) % 7
            candidate = (now + timedelta(days=days_ahead)).replace(
                hour=h, minute=m, second=0, microsecond=0
            )
            if candidate <= now:
                candidate += timedelta(weeks=1)
            return candidate

        raise RuntimeError(
            f"Job '{self._label}' has no schedule. "
            "Call .every(), .hourly(), .daily(), .daily_at(), etc."
        )

    def _advance_next_run(self, after: datetime) -> None:
        if self._interval:
            self._next_run = after + self._interval
        elif self._daily_hm:
            self._next_run = (after + timedelta(days=1)).replace(
                hour=self._daily_hm[0],
                minute=self._daily_hm[1],
                second=0,
                microsecond=0,
            )
        elif self._weekly_dhm:
            self._next_run = (after + timedelta(weeks=1)).replace(
                hour=self._weekly_dhm[1],
                minute=self._weekly_dhm[2],
                second=0,
                microsecond=0,
            )

    def is_due(self, now: datetime) -> bool:
        return self._next_run is not None and now >= self._next_run

    async def execute(self) -> None:
        log.debug("Scheduler: running job '%s'", self._label)
        try:
            result = self._fn()
            if inspect.isawaitable(result):
                await result
            now = datetime.now()
            self._advance_next_run(now)
            log.debug("Scheduler: job '%s' done, next run %s", self._label, self._next_run)
        except Exception as exc:
            log.error("Scheduler: job '%s' failed: %s", self._label, exc, exc_info=exc)
            # Advance next_run even on failure to avoid tight retry loops
            self._advance_next_run(datetime.now())


class Scheduler:
    """Code-based task scheduler — register jobs and run a background worker.

    Usage in FastAPI lifespan::

        from contextlib import asynccontextmanager
        from forgeapi import Scheduler

        scheduler = Scheduler()
        scheduler.call(send_daily_report).daily_at("09:00")
        scheduler.call(cleanup_temp).every(30)      # every 30 minutes
        scheduler.call(weekly_backup).weekly_on("sunday", at="03:00")

        @asynccontextmanager
        async def lifespan(app):
            task = asyncio.create_task(scheduler.run())
            yield
            task.cancel()

    Accepts both sync and async callables.
    """

    def __init__(self) -> None:
        self._jobs: list[ScheduledJob] = []

    def call(self, fn: Callable) -> ScheduledJob:
        """Register *fn* as a scheduled job and return its builder.

        Args:
            fn: Sync or async callable with no required arguments.

        Returns:
            :class:`ScheduledJob` — chain a timing method on it.
        """
        label = getattr(fn, "__name__", repr(fn))
        job = ScheduledJob(fn, label)
        self._jobs.append(job)
        return job

    async def run(self) -> None:
        """Start the scheduler loop — runs indefinitely.

        Schedule this as a background task during application startup::

            task = asyncio.create_task(scheduler.run())

        Cancel it on shutdown::

            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        """
        now = datetime.now()
        for job in self._jobs:
            if job._next_run is None:
                job._next_run = job._compute_first_next_run(now)
            log.debug(
                "Scheduler: job '%s' scheduled, first run at %s",
                job._label,
                job._next_run,
            )

        log.info("Scheduler started with %d job(s)", len(self._jobs))

        try:
            while True:
                now = datetime.now()
                due = [j for j in self._jobs if j.is_due(now)]
                if due:
                    await asyncio.gather(*(j.execute() for j in due))

                # Sleep until the next job is due (max 60s to avoid overshooting)
                next_runs = [
                    j._next_run for j in self._jobs if j._next_run is not None
                ]
                if next_runs:
                    soonest = min(next_runs)
                    sleep_secs = max(0.5, min((soonest - datetime.now()).total_seconds(), 60))
                else:
                    sleep_secs = 60

                await asyncio.sleep(sleep_secs)
        except asyncio.CancelledError:
            log.info("Scheduler stopped")
