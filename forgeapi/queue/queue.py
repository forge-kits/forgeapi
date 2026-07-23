from __future__ import annotations

import asyncio
import logging
import traceback
from datetime import datetime, timedelta

from .job import Job

log = logging.getLogger("forgeapi.queue")


class Queue:
    def __init__(self, name: str = "default", max_tries: int = 3) -> None:
        self._name = name
        self._max_tries = max_tries

    async def dispatch(self, job: Job, delay: int = 0) -> None:
        from .models import JobRecord

        available_at = datetime.now() + timedelta(seconds=delay)
        await JobRecord.create(
            queue=getattr(job, "queue", self._name),
            payload=job.serialize(),
            available_at=available_at,
        )
        log.debug("Queue: dispatched '%s'", job.serialize()["class"])

    async def run_next(self) -> bool:
        """Pick up and execute one pending job. Returns True if a job was processed."""
        from .models import FailedJob, JobRecord
        from tortoise.transactions import in_transaction

        now = datetime.now()

        async with in_transaction():
            record = await (
                JobRecord.filter(
                    reserved_at__isnull=True,
                    available_at__lte=now,
                    queue=self._name,
                )
                .order_by("id")
                .first()
            )

            if not record:
                return False

            record.reserved_at = now
            record.attempts += 1
            await record.save(update_fields=["reserved_at", "attempts"])

        job_class = record.payload.get("class", "unknown")

        try:
            job = Job.deserialize(record.payload)
            await job.handle()
            await record.delete()
            log.info("Queue: '%s' completed", job_class)
            return True

        except Exception:
            max_tries = getattr(job, "max_tries", self._max_tries) if "job" in dir() else self._max_tries
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
            else:
                backoff = (record.attempts ** 2) * 10
                record.reserved_at = None
                record.available_at = datetime.now() + timedelta(seconds=backoff)
                await record.save(update_fields=["reserved_at", "available_at"])
                log.info("Queue: '%s' will retry in %ds", job_class, backoff)

            return True

    async def work(self) -> None:
        """Infinite loop — use via ``forgeapi queue:work`` or FastAPI lifespan."""
        log.info("Queue worker started on queue '%s'", self._name)
        try:
            while True:
                processed = await self.run_next()
                if not processed:
                    await asyncio.sleep(1)
        except asyncio.CancelledError:
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
