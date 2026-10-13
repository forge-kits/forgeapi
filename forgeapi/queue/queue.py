from __future__ import annotations

import asyncio
import inspect
import logging
import traceback
from datetime import datetime, timedelta

from forgeapi.support.clock import to_db

from .job import Job

log = logging.getLogger("forgeapi.queue")
failed_log = logging.getLogger("forgeapi.queue.failed")


class Queue:
    def __init__(self, name: str = "default", max_tries: int = 3, timezone: str | None = None) -> None:
        self._name = name
        self._max_tries = max_tries
        self._timezone = timezone
        self._tz_resolved = timezone is not None
        self._hook_tasks: set[asyncio.Task] = set()

    @property
    def timezone(self) -> str | None:
        """IANA timezone: ``Queue(timezone=...)``, else ``timezone`` from
        ``config/project.py``, else the server's local time."""
        if not self._tz_resolved:
            from forgeapi.support.clock import config_timezone

            self._tz_resolved = True
            self._timezone = config_timezone()
        return self._timezone

    def now(self) -> datetime:
        """Current wall-clock time in the queue timezone (naive datetime)."""
        from forgeapi.support.clock import wall_clock_now

        return wall_clock_now(self.timezone)

    async def dispatch(self, job: Job, delay: int = 0) -> None:
        from .models import JobRecord

        available_at = self.now() + timedelta(seconds=delay)
        await JobRecord.create(
            queue=getattr(job, "queue", self._name),
            payload=job.serialize(),
            available_at=to_db(available_at),
        )
        log.debug("Queue: dispatched '%s'", job.serialize()["class"])

    async def run_next(self) -> bool:
        """Pick up and execute one pending job. Returns True if a job was processed."""
        from .models import FailedJob, JobRecord
        from tortoise.transactions import in_transaction

        now = self.now()

        async with in_transaction():
            record = await (
                JobRecord.filter(
                    reserved_at__isnull=True,
                    available_at__lte=to_db(now),
                    queue=self._name,
                )
                .select_for_update(skip_locked=True)
                .order_by("id")
                .first()
            )

            if not record:
                return False

            record.reserved_at = to_db(now)
            record.attempts += 1
            await record.save(update_fields=["reserved_at", "attempts"])

        job_class = record.payload.get("class", "unknown")
        job: Job | None = None

        try:
            job = Job.deserialize(record.payload)
            await job.handle()
            await record.delete()
            log.info("Queue: '%s' completed", job_class)
            return True

        except Exception as exc:
            max_tries = getattr(job, "max_tries", self._max_tries)
            log.error(
                "Queue: '%s' failed (attempt %d/%d)",
                job_class, record.attempts, max_tries,
            )

            if record.attempts >= max_tries:
                await FailedJob.create(
                    queue=record.queue,
                    payload=record.payload,
                    exception=traceback.format_exc(),
                )
                await record.delete()
                log.error("Queue: '%s' moved to failed_jobs", job_class)
                self._job_failed(job, job_class, record, exc)
            else:
                backoff = (record.attempts ** 2) * 10
                record.reserved_at = None
                record.available_at = to_db(self.now() + timedelta(seconds=backoff))
                await record.save(update_fields=["reserved_at", "available_at"])
                log.info("Queue: '%s' will retry in %ds", job_class, backoff)

            return True

    def _job_failed(self, job: Job | None, job_class: str, record, exc: BaseException) -> None:
        """Report a permanently failed job: always log, run ``Job.failed()`` in the background."""
        failed_log.error(
            "Job '%s' failed permanently on queue '%s' after %d attempt(s): %r",
            job_class, record.queue, record.attempts, exc,
        )
        if job is None:
            failed_log.error("Job '%s' could not be loaded, failed() hook skipped", job_class)
            return
        task = asyncio.create_task(self._run_failed_hook(job, job_class, exc))
        self._hook_tasks.add(task)  # strong ref: a bare task can be garbage-collected mid-run
        task.add_done_callback(self._hook_tasks.discard)

    @staticmethod
    async def _run_failed_hook(job: Job, job_class: str, exc: BaseException) -> None:
        timeout = getattr(job, "failed_timeout", 30)
        try:
            if inspect.iscoroutinefunction(job.failed):
                await asyncio.wait_for(job.failed(exc), timeout)
            else:
                await asyncio.wait_for(asyncio.to_thread(job.failed, exc), timeout)
        except asyncio.TimeoutError:
            failed_log.error("Job '%s' failed() hook timed out after %ss", job_class, timeout)
        except asyncio.CancelledError:
            failed_log.warning("Job '%s' failed() hook cancelled (worker stopping)", job_class)
            raise
        except Exception:
            failed_log.exception("Job '%s' failed() hook raised", job_class)

    async def wait_hooks(self) -> None:
        """Wait for running ``failed()`` hooks (each is bounded by ``failed_timeout``).

        Call before exiting a short-lived process such as ``queue:run``.
        """
        if self._hook_tasks:
            await asyncio.gather(*list(self._hook_tasks), return_exceptions=True)

    async def work(self) -> None:
        """Infinite loop — use via ``forgeapi queue:work`` or FastAPI lifespan."""
        log.info("Queue worker started on queue '%s'", self._name)
        try:
            while True:
                processed = await self.run_next()
                if not processed:
                    await asyncio.sleep(1)
        except asyncio.CancelledError:
            for task in list(self._hook_tasks):
                task.cancel()
            log.info("Queue worker stopped")


_queue = Queue()


async def dispatch(job: Job, *, delay: int = 0, queue: str | None = None) -> None:
    """Dispatch a job to the queue.

    Args:
        job:   Job instance to dispatch.
        delay: Seconds before the job becomes available.
        queue: Queue name override (defaults to ``job.queue`` or ``"default"``).
    """
    if queue is not None:
        job.queue = queue
    await _queue.dispatch(job, delay=delay)
