from __future__ import annotations

import asyncio
import importlib
import sys
from pathlib import Path

import typer

from forgeapi.cli.base import Command


class QueueCommand(Command):
    name = "queue"
    help_text = """\
Usage: forgeapi queue:<subcommand>

  queue:work [--queue=a,b]  Start the queue worker (infinite loop)
  queue:run  [--queue=a,b]  Process all pending jobs once
  queue:failed            List failed jobs
  queue:retry <id>        Move a failed job back to the queue
  queue:flush             Delete all failed jobs

--queue takes one or more queue names (comma-separated, highest priority first).
Default: "queue" from config/queue.py (or "default"). A Job goes to the queue named
in its `queue` attribute, so run a worker for every queue you use.

Examples:
  forgeapi queue:work --queue=emails
  forgeapi queue:work --queue=high,default
"""

    def handle(self, cmd: str, args: list[str]) -> None:
        sub = cmd.split(":", 1)[1] if ":" in cmd else ""

        if sub == "work":
            asyncio.run(self._work(self._parse_queue(args)))
        elif sub == "run":
            asyncio.run(self._run(self._parse_queue(args)))
        elif sub == "failed":
            asyncio.run(self._failed())
        elif sub == "retry":
            if not args:
                self.abort("Usage: forgeapi queue:retry <id>")
            asyncio.run(self._retry(int(args[0])))
        elif sub == "flush":
            asyncio.run(self._flush())
        else:
            self.show_help(cmd)

    # ── subcommands ───────────────────────────────────────────────────────────

    def _parse_queue(self, args: list[str]) -> str | None:
        """``--queue=a,b`` / ``--queue a,b`` -> "a,b"; None when absent (config default applies)."""
        for i, arg in enumerate(args):
            if arg.startswith("--queue="):
                value = arg.split("=", 1)[1]
            elif arg == "--queue" and i + 1 < len(args):
                value = args[i + 1]
            else:
                continue
            if not [n for n in value.split(",") if n.strip()]:
                self.abort("--queue needs a name.  Example: --queue=emails")
            return value
        if any(a.startswith("-") for a in args):
            self.abort(f"unknown option(s): {' '.join(a for a in args if a.startswith('-'))}")
        return None

    async def _work(self, queue: str | None = None) -> None:
        cfg = self._load_config()
        await self._connect_db(cfg)
        queue = queue or cfg.queue.queue
        typer.echo(f"Queue worker started on '{queue}'. Press Ctrl+C to stop.")
        try:
            from forgeapi.queue.queue import Queue
            await Queue(name=queue).work()
        except KeyboardInterrupt:
            pass
        finally:
            await self._disconnect_db()

    async def _run(self, queue: str | None = None) -> None:
        cfg = self._load_config()
        await self._connect_db(cfg)
        try:
            from forgeapi.queue.queue import Queue
            q = Queue(name=queue or cfg.queue.queue)
            count = 0
            while await q.run_next():
                count += 1
            await q.wait_hooks()
            typer.echo(f"Processed {count} job(s).")
        finally:
            await self._disconnect_db()

    async def _failed(self) -> None:
        cfg = self._load_config()
        await self._connect_db(cfg)
        try:
            from forgeapi.queue.models import FailedJob
            jobs = await FailedJob.all().order_by("-failed_at")
            if not jobs:
                typer.echo("No failed jobs.")
                return
            typer.echo(f"{'ID':<6}  {'Queue':<12}  {'Class':<45}  Failed At")
            typer.echo("-" * 90)
            for j in jobs:
                cls = j.payload.get("class", "unknown")
                typer.echo(f"{j.id:<6}  {j.queue:<12}  {cls:<45}  {j.failed_at}")
        finally:
            await self._disconnect_db()

    async def _retry(self, job_id: int) -> None:
        from forgeapi.support.clock import to_db, wall_clock_now

        cfg = self._load_config()
        await self._connect_db(cfg)
        try:
            from forgeapi.queue.models import FailedJob, JobRecord

            failed = await FailedJob.get_or_none(id=job_id)
            if not failed:
                self.abort(f"No failed job with id={job_id}.")

            record = JobRecord(queue=failed.queue, payload=failed.payload)
            record.available_at = to_db(wall_clock_now(cfg.project.timezone))
            await record.save()
            await failed.delete()
            typer.echo(f"Job {job_id} re-queued.")
        finally:
            await self._disconnect_db()

    async def _flush(self) -> None:
        cfg = self._load_config()
        await self._connect_db(cfg)
        try:
            from forgeapi.queue.models import FailedJob

            count = await FailedJob.all().count()
            await FailedJob.all().delete()
            typer.echo(f"Flushed {count} failed job(s).")
        finally:
            await self._disconnect_db()

    # ── helpers ───────────────────────────────────────────────────────────────

    def _load_config(self):
        sys.path.insert(0, str(Path.cwd()))
        try:
            from forgeapi.config import load_config
            return load_config()
        except Exception as exc:
            self.abort(f"Could not load config: {exc}")

    async def _connect_db(self, cfg) -> None:
        from tortoise import Tortoise

        module_dotted, attr = cfg.database.tortoise_orm.rsplit(".", 1)
        mod = importlib.import_module(module_dotted)
        tortoise_config = getattr(mod, attr)

        for app_cfg in tortoise_config.get("apps", {}).values():
            models_list = app_cfg.get("models", [])
            if "forgeapi.queue.models" not in models_list:
                models_list.append("forgeapi.queue.models")

        await Tortoise.init(config=tortoise_config)
        await Tortoise.generate_schemas(safe=True)

    @staticmethod
    async def _disconnect_db() -> None:
        from tortoise import Tortoise
        await Tortoise.close_connections()
