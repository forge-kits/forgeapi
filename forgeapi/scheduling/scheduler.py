from __future__ import annotations

import asyncio
import calendar
import inspect
import logging
from datetime import datetime, timedelta
from typing import Callable

from forgeapi.support.clock import naive_wall, to_db

log = logging.getLogger("forgeapi.scheduler")


class ScheduledJob:
    def __init__(self, fn: Callable, label: str) -> None:
        self._fn = fn
        self._label = label
        self._schedule_type: str | None = None
        self._schedule_config: dict = {}
        self._overlap_ttl: int | None = None  # minutes; None = overlapping allowed

    def name(self, label: str) -> "ScheduledJob":
        self._label = label
        return self

    def without_overlapping(self, expires_after: int = 1440) -> "ScheduledJob":
        """Skip a run while the previous one is still running (across scheduler instances).

        A skipped slot is not made up later. ``expires_after`` (minutes, default 24h)
        is the safety net: a lock left by a crashed process is ignored after that time,
        so set it above the job's longest expected runtime.
        """
        if expires_after < 1:
            raise ValueError("expires_after must be >= 1 minute.")
        self._overlap_ttl = expires_after
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

    def cron(self, expression: str) -> "ScheduledJob":
        """Standard 5-field cron, e.g. ``"*/5 * * * *"`` or ``"0 9 * * mon-fri"``."""
        from .cron import CronExpression

        CronExpression(expression)  # validate now, not at first run
        self._schedule_type = "cron"
        self._schedule_config = {"expression": expression}
        return self

    def monthly(self) -> "ScheduledJob":
        return self.monthly_on(1)

    def monthly_on(self, day: int = 1, at: str = "00:00") -> "ScheduledJob":
        """Run every month on ``day`` (clamped to the month's last day, e.g. 31 -> 30/28)."""
        if not 1 <= day <= 31:
            raise ValueError(f"Day of month must be 1-31, got {day}.")
        h, m = at.split(":")
        self._schedule_type = "monthly"
        self._schedule_config = {"day": day, "hour": int(h), "minute": int(m)}
        return self

    def yearly(self) -> "ScheduledJob":
        return self.yearly_on(1, 1)

    def yearly_on(self, month: int = 1, day: int = 1, at: str = "00:00", every: int = 1) -> "ScheduledJob":
        """Run every ``every`` years on ``month``/``day`` (Feb 29 falls back to Feb 28)."""
        if not 1 <= month <= 12:
            raise ValueError(f"Month must be 1-12, got {month}.")
        if not 1 <= day <= 31:
            raise ValueError(f"Day must be 1-31, got {day}.")
        if every < 1:
            raise ValueError("`every` must be >= 1.")
        h, m = at.split(":")
        self._schedule_type = "yearly"
        self._schedule_config = {
            "month": month, "day": day, "hour": int(h), "minute": int(m), "years": every,
        }
        return self

    def every_two_years(self, month: int = 1, day: int = 1, at: str = "00:00") -> "ScheduledJob":
        return self.yearly_on(month, day, at, every=2)

    @staticmethod
    def _at(year: int, month: int, day: int, h: int, m: int) -> datetime:
        day = min(day, calendar.monthrange(year, month)[1])
        return datetime(year, month, day, h, m)

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
        if self._schedule_type == "cron":
            from .cron import CronExpression

            return CronExpression(self._schedule_config["expression"]).next_after(after)
        if self._schedule_type == "monthly":
            c = self._schedule_config
            y, mo = after.year, after.month
            candidate = self._at(y, mo, c["day"], c["hour"], c["minute"])
            if candidate <= after:
                y, mo = (y + 1, 1) if mo == 12 else (y, mo + 1)
                candidate = self._at(y, mo, c["day"], c["hour"], c["minute"])
            return candidate
        if self._schedule_type == "yearly":
            c = self._schedule_config
            candidate = self._at(after.year, c["month"], c["day"], c["hour"], c["minute"])
            if candidate <= after:
                candidate = self._at(
                    after.year + c.get("years", 1), c["month"], c["day"], c["hour"], c["minute"]
                )
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

    Add ``forgeapi.scheduling.models`` to your Tortoise ``apps`` so the table is created::

        "models": ["database.models", "forgeapi.scheduling.models", "forgeapi.permissions.models"]

    Times use the ``timezone`` from ``config/project.py`` (or ``Scheduler(timezone="Europe/Sofia")``);
    without either, the server's local time.

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

    def __init__(self, timezone: str | None = None) -> None:
        self._jobs: list[ScheduledJob] = []
        self._timezone = timezone
        self._tz_resolved = timezone is not None

    @property
    def timezone(self) -> str | None:
        """IANA timezone used for schedules: ``Scheduler(timezone=...)``, else
        ``timezone`` from ``config/project.py``, else the server's local time."""
        if not self._tz_resolved:
            from forgeapi.support.clock import config_timezone

            self._tz_resolved = True
            self._timezone = config_timezone()
        return self._timezone

    def now(self) -> datetime:
        """Current wall-clock time in the scheduler timezone, as a naive datetime.

        All ``next_run_at`` / ``last_run_at`` values are stored in this wall-clock
        time, so changing the timezone shifts stored schedules accordingly.
        """
        from forgeapi.support.clock import wall_clock_now

        return wall_clock_now(self.timezone)

    def call(self, fn: Callable) -> ScheduledJob:
        label = getattr(fn, "__name__", repr(fn))
        job = ScheduledJob(fn, label)
        self._jobs.append(job)
        return job

    @property
    def registry(self) -> dict[str, ScheduledJob]:
        return {job._label: job for job in self._jobs}

    def _is_locked(self, record, job: ScheduledJob, now: datetime) -> bool:
        """True when ``job`` is without_overlapping() and a non-expired run is in progress."""
        if job._overlap_ttl is None or record.running_since is None:
            return False
        age = now - naive_wall(record.running_since)
        return age < timedelta(minutes=job._overlap_ttl)

    async def _release(self, record, job: ScheduledJob) -> None:
        if job._overlap_ttl is not None:
            record.running_since = None
            await record.save(update_fields=["running_since"])

    async def sync(self) -> None:
        """Upsert all registered jobs into the DB. Call once on startup."""
        from .models import ScheduledTask

        now = self.now()
        for job in self._jobs:
            if job._schedule_type is None:
                raise RuntimeError(
                    f"Job '{job._label}' has no schedule. "
                    "Call .every(), .daily_at(), .weekly_on(), etc."
                )
            # next_run_at is assigned after creation, not passed to get_or_create(): Model.__init__
            # strips tzinfo when use_tz=False, which PostgreSQL then reads as host-local time.
            record, created = await ScheduledTask.get_or_create(
                name=job._label,
                defaults={
                    "schedule_type": job._schedule_type,
                    "schedule_config": job._schedule_config,
                    "is_enabled": True,
                },
            )
            fields = ["schedule_type", "schedule_config"]
            if not created:
                record.schedule_type = job._schedule_type
                record.schedule_config = job._schedule_config
            if record.next_run_at is None:
                record.next_run_at = to_db(job.compute_next_run(now))
                fields.append("next_run_at")
            await record.save(update_fields=fields)

            log.debug("Scheduler: '%s' synced, next run at %s", job._label, record.next_run_at)

    async def run_due(self) -> int:
        """Execute all currently due tasks. Returns number of tasks run.

        Claiming (row lock + advancing ``next_run_at``) happens in its own
        short transaction before the job runs, so multiple scheduler
        instances can't pick up and execute the same due task twice.
        """
        from tortoise.transactions import in_transaction

        from .models import ScheduledTask

        registry = self.registry
        now = self.now()

        due_ids = await ScheduledTask.filter(
            is_enabled=True, next_run_at__lte=to_db(now)
        ).values_list("id", flat=True)
        if not due_ids:
            return 0

        ran = 0
        for task_id in due_ids:
            async with in_transaction():
                record = await (
                    ScheduledTask.filter(id=task_id, is_enabled=True, next_run_at__lte=to_db(now))
                    .select_for_update(skip_locked=True)
                    .first()
                )
                if record is None:
                    continue  # claimed by another instance, or no longer due

                job = registry.get(record.name)
                if job is None:
                    log.warning("Scheduler: task '%s' in DB has no registered callable", record.name)
                    continue

                record.next_run_at = to_db(job.compute_next_run(now))
                if self._is_locked(record, job, now):
                    await record.save(update_fields=["next_run_at"])
                    log.info("Scheduler: '%s' skipped — previous run still in progress", record.name)
                    continue
                if job._overlap_ttl is not None:
                    record.running_since = to_db(now)
                    await record.save(update_fields=["next_run_at", "running_since"])
                else:
                    await record.save(update_fields=["next_run_at"])

            try:
                status, error = await job.execute()
            finally:
                await self._release(record, job)
            run_at = self.now()
            record.last_run_at = to_db(run_at)
            record.last_status = status
            record.last_error = error
            await record.save(update_fields=["last_run_at", "last_status", "last_error"])
            log.debug("Scheduler: '%s' %s, next run at %s", record.name, status, record.next_run_at)
            ran += 1

        return ran

    async def run_one(self, name: str) -> None:
        """Run a specific task by name, regardless of schedule."""
        from .models import ScheduledTask

        registry = self.registry
        job = registry.get(name)
        if job is None:
            raise ValueError(f"No job registered with name '{name}'.")

        from tortoise.transactions import in_transaction

        locked_record = None
        if job._overlap_ttl is not None:
            async with in_transaction():
                locked_record = await ScheduledTask.filter(name=name).select_for_update().first()
                if locked_record is not None:
                    if self._is_locked(locked_record, job, self.now()):
                        raise ValueError(f"'{name}' is already running (without_overlapping).")
                    locked_record.running_since = to_db(self.now())
                    await locked_record.save(update_fields=["running_since"])

        try:
            status, error = await job.execute()
        finally:
            if locked_record is not None:
                await self._release(locked_record, job)
        run_at = self.now()

        record = await ScheduledTask.get_or_none(name=name)
        if record:
            record.last_run_at = to_db(run_at)
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
                from forgeapi.support.clock import naive_wall

                soonest = await ScheduledTask.filter(
                    is_enabled=True, next_run_at__isnull=False
                ).order_by("next_run_at").first()

                if soonest and soonest.next_run_at:
                    sleep_secs = max(
                        0.5,
                        min((naive_wall(soonest.next_run_at) - self.now()).total_seconds(), 60)
                    )
                else:
                    sleep_secs = 60

                await asyncio.sleep(sleep_secs)
        except asyncio.CancelledError:
            log.info("Scheduler stopped")
