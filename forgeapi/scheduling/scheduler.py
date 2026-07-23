from __future__ import annotations

import asyncio
import inspect
import logging
from datetime import datetime, timedelta
from typing import Callable

log = logging.getLogger("forgeapi.scheduler")


class ScheduledJob:
    def __init__(self, fn: Callable, label: str) -> None:
        self._fn = fn
        self._label = label
        self._schedule_type: str | None = None
        self._schedule_config: dict = {}

    def name(self, label: str) -> "ScheduledJob":
        self._label = label
        return self

    def every_minute(self) -> "ScheduledJob":
        self._schedule_type = "interval"
        self._schedule_config = {"minutes": 1}
        return self

    def every(self, minutes: int) -> "ScheduledJob":
        self._schedule_type = "interval"
        self._schedule_config = {"minutes": minutes}
        return self

    def every_hours(self, hours: int = 1) -> "ScheduledJob":
        self._schedule_type = "interval"
        self._schedule_config = {"minutes": hours * 60}
        return self

    def hourly(self) -> "ScheduledJob":
        return self.every_hours(1)

    def daily(self) -> "ScheduledJob":
        return self.daily_at("00:00")

    def daily_at(self, time: str) -> "ScheduledJob":
        h, m = time.split(":")
        self._schedule_type = "daily"
        self._schedule_config = {"hour": int(h), "minute": int(m)}
        return self

    def weekly(self) -> "ScheduledJob":
        return self.weekly_on("monday")

    def weekly_on(self, day: str, at: str = "00:00") -> "ScheduledJob":
        days = {
            "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
            "friday": 4, "saturday": 5, "sunday": 6,
        }
        idx = days.get(day.lower())
        if idx is None:
            raise ValueError(f"Unknown day '{day}'.")
        h, m = at.split(":")
        self._schedule_type = "weekly"
        self._schedule_config = {"weekday": idx, "hour": int(h), "minute": int(m)}
        return self

    def compute_next_run(self, after: datetime) -> datetime:
        if self._schedule_type == "interval":
            return after + timedelta(minutes=self._schedule_config["minutes"])
        if self._schedule_type == "daily":
            h, m = self._schedule_config["hour"], self._schedule_config["minute"]
            candidate = after.replace(hour=h, minute=m, second=0, microsecond=0)
            if candidate <= after:
                candidate += timedelta(days=1)
            return candidate
        if self._schedule_type == "weekly":
            target_wd = self._schedule_config["weekday"]
            h, m = self._schedule_config["hour"], self._schedule_config["minute"]
            days_ahead = (target_wd - after.weekday()) % 7
            candidate = (after + timedelta(days=days_ahead)).replace(
                hour=h, minute=m, second=0, microsecond=0
            )
            if candidate <= after:
                candidate += timedelta(weeks=1)
            return candidate
        raise RuntimeError(
            f"Job '{self._label}' has no schedule. "
            "Call .every(), .hourly(), .daily(), .daily_at(), etc."
        )

    async def execute(self) -> tuple[str, str | None]:
        log.debug("Scheduler: running '%s'", self._label)
        try:
            result = self._fn()
            if inspect.isawaitable(result):
                await result
            log.debug("Scheduler: '%s' succeeded", self._label)
            return "success", None
        except Exception as exc:
            log.error("Scheduler: '%s' failed: %s", self._label, exc, exc_info=exc)
            return "failed", str(exc)


class Scheduler:
    """DB-backed task scheduler — define jobs in ``schedule.py``.

    Jobs are declared in code; state (next_run_at, last_run_at, status, errors)
    is persisted in the ``scheduled_tasks`` table.

    Add ``forgeapi.scheduling`` to your Tortoise ``apps`` so the table is created::

        "models": ["database.models", "forgeapi.scheduling", "forgeapi.permissions.models"]

    Define jobs in ``schedule.py`` at the project root::

        from forgeapi import Scheduler

        scheduler = Scheduler()

        scheduler.call(send_report).daily_at("09:00").name("send-report")
        scheduler.call(cleanup).every(30).name("cleanup")

    Run via CLI or lifespan::

        # cron every minute:
        forgeapi schedule:run

        # dev loop:
        forgeapi schedule:work

        # run specific task manually:
        forgeapi schedule:run send-report

        # or in FastAPI lifespan:
        task = asyncio.create_task(scheduler.run())
    """

    def __init__(self) -> None:
        self._jobs: list[ScheduledJob] = []

    def call(self, fn: Callable) -> ScheduledJob:
        label = getattr(fn, "__name__", repr(fn))
        job = ScheduledJob(fn, label)
        self._jobs.append(job)
        return job

    @property
    def registry(self) -> dict[str, ScheduledJob]:
        return {job._label: job for job in self._jobs}

    async def sync(self) -> None:
        """Upsert all registered jobs into the DB. Call once on startup."""
        from .models import ScheduledTask

        now = datetime.now()
        for job in self._jobs:
            if job._schedule_type is None:
                raise RuntimeError(
                    f"Job '{job._label}' has no schedule. "
                    "Call .every(), .daily_at(), .weekly_on(), etc."
                )
            record, created = await ScheduledTask.get_or_create(
                name=job._label,
                defaults={
                    "schedule_type": job._schedule_type,
                    "schedule_config": job._schedule_config,
                    "next_run_at": job.compute_next_run(now),
                    "is_enabled": True,
                },
            )
            if not created:
                record.schedule_type = job._schedule_type
                record.schedule_config = job._schedule_config
                if record.next_run_at is None:
                    record.next_run_at = job.compute_next_run(now)
                await record.save(update_fields=["schedule_type", "schedule_config", "next_run_at"])

            log.debug("Scheduler: '%s' synced, next run at %s", job._label, record.next_run_at)

    async def run_due(self) -> int:
        """Execute all currently due tasks. Returns number of tasks run."""
        from .models import ScheduledTask

        registry = self.registry
        now = datetime.now()

        due = await ScheduledTask.filter(is_enabled=True, next_run_at__lte=now).all()
        if not due:
            return 0

        for record in due:
            job = registry.get(record.name)
            if job is None:
                log.warning("Scheduler: task '%s' in DB has no registered callable", record.name)
                continue

            status, error = await job.execute()
            run_at = datetime.now()
            record.last_run_at = run_at
            record.last_status = status
            record.last_error = error
            record.next_run_at = job.compute_next_run(run_at)
            await record.save(
                update_fields=["last_run_at", "last_status", "last_error", "next_run_at"]
            )
            log.debug("Scheduler: '%s' %s, next run at %s", record.name, status, record.next_run_at)

        return len(due)

    async def run_one(self, name: str) -> None:
        """Run a specific task by name, regardless of schedule."""
        from .models import ScheduledTask

        registry = self.registry
        job = registry.get(name)
        if job is None:
            raise ValueError(f"No job registered with name '{name}'.")

        status, error = await job.execute()
        run_at = datetime.now()

        record = await ScheduledTask.get_or_none(name=name)
        if record:
            record.last_run_at = run_at
            record.last_status = status
            record.last_error = error
            await record.save(update_fields=["last_run_at", "last_status", "last_error"])

    async def run(self) -> None:
        """Infinite loop — use in FastAPI lifespan or forgeapi schedule:work."""
        await self.sync()
        log.info("Scheduler started with %d job(s)", len(self._jobs))

        try:
            while True:
                await self.run_due()

                from .models import ScheduledTask
                soonest = await ScheduledTask.filter(
                    is_enabled=True, next_run_at__isnull=False
                ).order_by("next_run_at").first()

                if soonest and soonest.next_run_at:
                    sleep_secs = max(
                        0.5,
                        min((soonest.next_run_at - datetime.now()).total_seconds(), 60)
                    )
                else:
                    sleep_secs = 60

                await asyncio.sleep(sleep_secs)
        except asyncio.CancelledError:
            log.info("Scheduler stopped")
