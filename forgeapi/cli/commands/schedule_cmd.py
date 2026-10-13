from __future__ import annotations

import asyncio
import importlib
import importlib.util
import sys
from datetime import datetime, timedelta
from pathlib import Path

from forgeapi.cli.base import Command


class ScheduleCommand(Command):
    name = "schedule"
    help_text = """\
Usage: forgeapi schedule:<subcommand>

  schedule:run              Run all due tasks once (use with cron: */1 * * * *)
  schedule:run <name>       Run a specific task manually by name
  schedule:work             Run the scheduler loop (dev mode, no cron needed)
  schedule:list             List all registered tasks and their status

Frequencies (define in schedule.py):
  .every_minute()  .every(n)  .hourly()  .every_hours(n)
  .daily()  .daily_at("HH:MM")
  .weekly()  .weekly_on("day", at="HH:MM")
  .monthly()  .monthly_on(day, at="HH:MM")
  .yearly()  .yearly_on(month, day, at="HH:MM")
  .every_two_years(month, day, at="HH:MM")
  .cron("*/5 * * * *")

Examples:
  forgeapi schedule:run
  forgeapi schedule:run send-report
  forgeapi schedule:work
  forgeapi schedule:list
"""

    def handle(self, cmd: str, args: list[str]) -> None:
        subcmd = cmd.split(":", 1)[1] if ":" in cmd else ""

        if subcmd == "run":
            task_name = next((a for a in args if not a.startswith("-")), None)
            asyncio.run(self._run(task_name))
        elif subcmd == "work":
            asyncio.run(self._work())
        elif subcmd == "list":
            asyncio.run(self._list())
        else:
            self.abort(
                f"unknown schedule command '{cmd}'.\n"
                "  Available: schedule:run, schedule:work, schedule:list"
            )

    # ── Subcommand handlers ─────────────────────────────────────────────────────

    async def _run(self, task_name: str | None) -> None:
        import typer

        scheduler, cfg = self._load()
        await self._connect_db(cfg)

        try:
            await scheduler.sync()

            if task_name:
                typer.echo(f"Running '{task_name}'...")
                try:
                    await scheduler.run_one(task_name)
                    typer.echo("Done.")
                except ValueError as exc:
                    self.abort(str(exc))
            else:
                count = await scheduler.run_due()
                typer.echo(f"Ran {count} due task(s).")
        finally:
            await self._disconnect_db()

    async def _work(self) -> None:
        import typer

        scheduler, cfg = self._load()
        await self._connect_db(cfg)

        typer.echo(f"Scheduler running ({len(scheduler._jobs)} job(s)). Press Ctrl+C to stop.")
        try:
            await scheduler.run()
        except KeyboardInterrupt:
            typer.echo("\nStopped.")
        finally:
            await self._disconnect_db()

    async def _list(self) -> None:
        import typer

        scheduler, cfg = self._load()
        await self._connect_db(cfg)

        try:
            await scheduler.sync()

            from forgeapi.scheduling.models import ScheduledTask
            records = await ScheduledTask.all().order_by("name")
            registry = scheduler.registry

            if not records:
                typer.echo("No scheduled tasks found.")
                return

            col_name   = max(len(r.name) for r in records)
            col_name   = max(col_name, 4)
            col_sched  = max(
                [8] + [len(self._describe_schedule(registry[r.name])) for r in records if r.name in registry]
            )

            typer.echo("")
            typer.echo(
                f"  {'NAME':<{col_name}}  {'SCHEDULE':<{col_sched}}  {'LAST RUN':<32}  {'NEXT RUN':<32}  STATUS"
            )
            typer.echo("  " + "-" * (col_name + col_sched + 32 + 32 + 14))

            for record in records:
                job = registry.get(record.name)
                schedule_str = self._describe_schedule(job) if job else "—"
                from forgeapi.support.clock import naive_wall

                now = scheduler.now()
                last_at = naive_wall(record.last_run_at) if record.last_run_at else None
                next_at = naive_wall(record.next_run_at) if record.next_run_at else None
                last_run = (
                    f"{last_at:%Y-%m-%d %H:%M:%S} ({self._humanize(now - last_at)})"
                    if last_at else "never"
                )
                next_run = (
                    f"{next_at:%Y-%m-%d %H:%M:%S} ({self._humanize(next_at - now, future=True)})"
                    if next_at else "—"
                )
                status = record.last_status or "—"

                typer.echo(
                    f"  {record.name:<{col_name}}  {schedule_str:<{col_sched}}  {last_run:<32}  {next_run:<32}  {status}"
                )

            typer.echo("")
        finally:
            await self._disconnect_db()

    # ── Helpers ─────────────────────────────────────────────────────────────────

    @staticmethod
    def _humanize(delta: timedelta, future: bool = False) -> str:
        """Format a duration as ``in 2d 3h`` / ``5m 10s ago``. Keeps the two largest units."""
        total = int(delta.total_seconds())
        if total <= 0:
            return "now" if future else "just now"
        parts = []
        for unit, size in (("d", 86400), ("h", 3600), ("m", 60), ("s", 1)):
            value, total = divmod(total, size)
            if value:
                parts.append(f"{value}{unit}")
        text = " ".join(parts[:2])
        return f"in {text}" if future else f"{text} ago"

    def _load(self):
        """Import schedule.py and return (scheduler, cfg)."""
        from forgeapi.config import load_config
        cfg = load_config()

        schedule_file = getattr(cfg.structure, "schedule_file", "schedule.py")
        path = Path(schedule_file)

        if not path.exists():
            self.abort(
                f"'{schedule_file}' not found. "
                "Create it and define a `scheduler` variable:\n\n"
                "  from forgeapi import Scheduler\n"
                "  scheduler = Scheduler()\n"
                "  scheduler.call(my_task).daily_at('09:00').name('my-task')"
            )

        cwd = str(Path.cwd())
        if cwd not in sys.path:
            sys.path.insert(0, cwd)

        spec = importlib.util.spec_from_file_location("_schedule", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        scheduler = getattr(mod, "scheduler", None)
        if scheduler is None:
            self.abort(f"'{schedule_file}' must define a `scheduler` variable.")

        from forgeapi.scheduling import Scheduler
        if not isinstance(scheduler, Scheduler):
            self.abort(f"`scheduler` in '{schedule_file}' must be a Scheduler instance.")

        return scheduler, cfg

    @staticmethod
    async def _connect_db(cfg) -> None:
        from tortoise import Tortoise
        module_dotted, attr = cfg.database.tortoise_orm.rsplit(".", 1)
        mod = importlib.import_module(module_dotted)
        tortoise_config = getattr(mod, attr)

        # Ensure forgeapi.scheduling.models is in the models list so ScheduledTask is registered
        for app_cfg in tortoise_config.get("apps", {}).values():
            models_list = app_cfg.get("models", [])
            if "forgeapi.scheduling.models" not in models_list:
                models_list.append("forgeapi.scheduling.models")

        await Tortoise.init(config=tortoise_config)
        await Tortoise.generate_schemas(safe=True)

    @staticmethod
    async def _disconnect_db() -> None:
        from tortoise import Tortoise
        await Tortoise.close_connections()

    @staticmethod
    def _describe_schedule(job) -> str:
        t = job._schedule_type
        c = job._schedule_config
        if t == "interval":
            m = c["minutes"]
            if m == 1:
                return "every minute"
            if m % 60 == 0:
                h = m // 60
                return f"every {h}h" if h > 1 else "every hour"
            return f"every {m}m"
        if t == "daily":
            return f"daily at {c['hour']:02d}:{c['minute']:02d}"
        if t == "weekly":
            days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
            return f"weekly {days[c['weekday']]} {c['hour']:02d}:{c['minute']:02d}"
        if t == "cron":
            return f"cron {c['expression']}"
        if t == "monthly":
            return f"monthly on day {c['day']} {c['hour']:02d}:{c['minute']:02d}"
        if t == "yearly":
            n = c.get("years", 1)
            every = "yearly" if n == 1 else f"every {n} years"
            return f"{every} on {c['day']:02d}.{c['month']:02d} {c['hour']:02d}:{c['minute']:02d}"
        return "—"
