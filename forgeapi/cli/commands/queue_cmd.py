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

  queue:work              Start the queue worker (infinite loop)
  queue:run               Process all pending jobs once
  queue:failed            List failed jobs
  queue:retry <id>        Move a failed job back to the queue
  queue:flush             Delete all failed jobs
"""

    def handle(self, cmd: str, args: list[str]) -> None:
        sub = cmd.split(":", 1)[1] if ":" in cmd else ""

        if sub == "work":
            asyncio.run(self._work())
        elif sub == "run":
            asyncio.run(self._run())
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

    async def _work(self) -> None:
        cfg = self._load_config()
        await self._connect_db(cfg)
        typer.echo("Queue worker started. Press Ctrl+C to stop.")
        try:
            from forgeapi.queue.queue import Queue
            await Queue().work()
        except KeyboardInterrupt:
            pass
        finally:
            await self._disconnect_db()

    async def _run(self) -> None:
        cfg = self._load_config()
        await self._connect_db(cfg)
        try:
            from forgeapi.queue.queue import Queue
            q = Queue()
            count = 0
            while await q.run_next():
                count += 1
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
        from datetime import datetime

        cfg = self._load_config()
        await self._connect_db(cfg)
        try:
            from forgeapi.queue.models import FailedJob, JobRecord

            failed = await FailedJob.get_or_none(id=job_id)
            if not failed:
                self.abort(f"No failed job with id={job_id}.")

            await JobRecord.create(
                queue=failed.queue,
                payload=failed.payload,
                available_at=datetime.now(),
            )
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
