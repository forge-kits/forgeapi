from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path

from forgeapi.foundation import Provider
from forgeapi.logging import log

_log = log.channel("scheduling.provider")


class SchedulerProvider(Provider):
    """Loads ``schedule.py`` and runs the Scheduler in a background task.

    Activated when ``config/scheduler.py`` exists::

        # config/scheduler.py
        config = {
            "enabled": True,
            "schedule": "schedule.py",  # path to your schedule definition
        }

    Your ``schedule.py`` must define a ``scheduler`` variable::

        from forgeapi import Scheduler

        scheduler = Scheduler()
        scheduler.call(cleanup).every(30).name("cleanup")
        scheduler.call(report).daily_at("09:00").name("report")

    The provider calls ``scheduler.run()`` on startup (which syncs jobs to DB
    then loops until cancelled) and cancels the task on shutdown.
    """

    _task: asyncio.Task | None = None

    def boot(self) -> None:
        cfg = self.config.scheduler
        if not cfg.enabled:
            _log.debug("SchedulerProvider: disabled via config")
            return

        schedule_path = Path(cfg.schedule)
        if not schedule_path.exists():
            _log.warning(
                "SchedulerProvider: schedule file '%s' not found — scheduler not started",
                cfg.schedule,
            )
            return

        scheduler = self._load_scheduler(schedule_path)
        if scheduler is None:
            return

        self._register_lifespan(scheduler, cfg.schedule)

    # ------------------------------------------------------------------

    def _load_scheduler(self, path: Path):
        spec = importlib.util.spec_from_file_location("_forgeapi_schedule", path)
        if spec is None or spec.loader is None:
            _log.error("SchedulerProvider: cannot load '%s'", path)
            return None
        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
        except Exception as exc:
            _log.error("SchedulerProvider: error executing '%s': %s", path, exc)
            return None

        scheduler = getattr(module, "scheduler", None)
        if scheduler is None:
            _log.error(
                "SchedulerProvider: '%s' must define a `scheduler` variable "
                "(e.g. scheduler = Scheduler())",
                path,
            )
            return None
        return scheduler

    def _register_lifespan(self, scheduler, schedule_label: str) -> None:
        provider = self

        async def _startup() -> None:
            provider._task = asyncio.create_task(
                scheduler.run(), name="forgeapi:scheduler"
            )
            _log.info("SchedulerProvider: started  schedule=%s", schedule_label)

        async def _shutdown() -> None:
            if provider._task and not provider._task.done():
                provider._task.cancel()
                try:
                    await provider._task
                except asyncio.CancelledError:
                    pass
            provider._task = None
            _log.info("SchedulerProvider: stopped")

        self.app.add_event_handler("startup", _startup)
        self.app.add_event_handler("shutdown", _shutdown)
        _log.debug("SchedulerProvider: lifespan hooks registered")
