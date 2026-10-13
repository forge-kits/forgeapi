"""Job.failed() hook: runs in background, never blocks or breaks the worker."""
import asyncio
import logging
import time

import pytest
from tortoise import Tortoise
import tortoise.timezone as tt

from forgeapi.queue import FailedJob, Job, JobRecord, Queue

CALLS: list = []


class Boom(Job):
    max_tries = 1

    def __init__(self, n=1):
        self.n = n

    async def handle(self):
        raise RuntimeError("boom")

    async def failed(self, exception):
        CALLS.append(("async", self.n, str(exception)))


class SyncHook(Boom):
    def failed(self, exception):
        time.sleep(0.2)  # blocking on purpose: must not stall the event loop
        CALLS.append(("sync", self.n, str(exception)))


class SlowHook(Boom):
    failed_timeout = 0.2

    async def failed(self, exception):
        await asyncio.sleep(5)
        CALLS.append(("slow-finished",))


class BrokenHook(Boom):
    async def failed(self, exception):
        raise ValueError("hook bug")


class Retrying(Boom):
    max_tries = 3


def run(coro_fn):
    async def scenario():
        await Tortoise.init(config={
            "connections": {"default": "sqlite://:memory:"},
            "apps": {"models": {"models": ["forgeapi.queue.models"], "default_connection": "default"}},
        })
        await Tortoise.generate_schemas()
        try:
            await coro_fn()
        finally:
            await Tortoise.close_connections()
            tt._reset_timezone_cache()

    CALLS.clear()
    asyncio.run(scenario())


def test_hook_called_after_final_failure():
    async def body():
        q = Queue(timezone="UTC")
        await q.dispatch(Boom(7))
        assert await q.run_next() is True
        await q.wait_hooks()
        assert CALLS == [("async", 7, "boom")]
        assert await FailedJob.all().count() == 1
        assert await JobRecord.all().count() == 0

    run(body)


def test_hook_not_called_while_retries_remain():
    async def body():
        q = Queue(timezone="UTC")
        await q.dispatch(Retrying())
        await q.run_next()
        await q.wait_hooks()
        assert CALLS == []
        assert await FailedJob.all().count() == 0

    run(body)


def test_sync_hook_does_not_block_worker():
    async def body():
        q = Queue(timezone="UTC")
        await q.dispatch(SyncHook(1))
        started = time.monotonic()
        await q.run_next()
        assert time.monotonic() - started < 0.15  # hook sleeps 0.2s in a thread
        await q.wait_hooks()
        assert CALLS == [("sync", 1, "boom")]

    run(body)


def test_slow_hook_is_cancelled_after_timeout(caplog):
    async def body():
        q = Queue(timezone="UTC")
        await q.dispatch(SlowHook())
        started = time.monotonic()
        await q.run_next()
        await q.wait_hooks()
        assert time.monotonic() - started < 2
        assert CALLS == []
        assert any("timed out" in r.getMessage() for r in caplog.records)

    with caplog.at_level(logging.ERROR, logger="forgeapi.queue.failed"):
        run(body)


def test_hook_error_is_logged_not_raised(caplog):
    async def body():
        q = Queue(timezone="UTC")
        await q.dispatch(BrokenHook())
        assert await q.run_next() is True
        await q.wait_hooks()
        assert any("hook raised" in r.getMessage() for r in caplog.records)
        assert await FailedJob.all().count() == 1

    with caplog.at_level(logging.ERROR, logger="forgeapi.queue.failed"):
        run(body)


def test_unloadable_job_is_logged_without_hook(caplog):
    async def body():
        await JobRecord.create(
            queue="default",
            payload={"class": "no_such_module.Missing", "data": {}},
            available_at=__import__("forgeapi.support.clock", fromlist=["x"]).to_db(
                __import__("datetime").datetime(2000, 1, 1)),
        )
        q = Queue(max_tries=1, timezone="UTC")
        assert await q.run_next() is True
        await q.wait_hooks()
        assert await FailedJob.all().count() == 1
        msgs = [r.getMessage() for r in caplog.records]
        assert any("failed permanently" in m for m in msgs)
        assert any("could not be loaded" in m for m in msgs)

    with caplog.at_level(logging.ERROR, logger="forgeapi.queue.failed"):
        run(body)


# ── stuck job recovery ────────────────────────────────────────────────────────

class Counted(Job):
    max_tries = 3

    async def handle(self):
        CALLS.append("ran")


class Exhausted(Job):
    max_tries = 2

    async def handle(self):
        CALLS.append("ran")

    async def failed(self, exception):
        CALLS.append(("failed", type(exception).__name__))


async def _reserved(job, *, seconds_ago, attempts):
    from datetime import datetime, timedelta
    from forgeapi.support.clock import to_db

    q = Queue(timezone="UTC", retry_after=60)
    await q.dispatch(job)
    rec = await JobRecord.first()
    rec.reserved_at = to_db(q.now() - timedelta(seconds=seconds_ago))
    rec.attempts = attempts
    await rec.save(update_fields=["reserved_at", "attempts"])
    return q


def test_stuck_job_is_retried_after_retry_after():
    async def body():
        q = await _reserved(Counted(), seconds_ago=120, attempts=1)
        assert await q.run_next() is True
        assert CALLS == ["ran"]
        assert await JobRecord.all().count() == 0

    run(body)


def test_recently_reserved_job_is_left_alone():
    async def body():
        q = await _reserved(Counted(), seconds_ago=10, attempts=1)
        assert await q.run_next() is False
        assert CALLS == []
        assert await JobRecord.all().count() == 1

    run(body)


def test_stuck_job_out_of_attempts_goes_to_failed_without_running():
    async def body():
        q = await _reserved(Exhausted(), seconds_ago=120, attempts=2)  # both tries died mid-job
        assert await q.run_next() is True
        await q.wait_hooks()
        assert "ran" not in CALLS
        assert CALLS == [("failed", "MaxAttemptsExceeded")]
        assert await FailedJob.all().count() == 1
        assert await JobRecord.all().count() == 0

    run(body)


# ── several queues / --queue ──────────────────────────────────────────────────

class Emails(Job):
    queue = "emails"

    async def handle(self):
        CALLS.append("emails")


class High(Job):
    queue = "high"

    async def handle(self):
        CALLS.append("high")


class Normal(Job):
    async def handle(self):
        CALLS.append("default")


def test_queue_names_parsing():
    assert Queue(name="a, b")._names == ["a", "b"]
    assert Queue(name=["x"])._names == ["x"]
    assert Queue()._names == ["default"]
    with pytest.raises(ValueError):
        Queue(name=" , ")


def test_worker_only_takes_its_own_queues():
    async def body():
        q = Queue(name="emails", timezone="UTC")
        await q.dispatch(Normal()); await q.dispatch(Emails())
        assert await q.run_next() is True
        assert await q.run_next() is False
        assert CALLS == ["emails"]
        assert await JobRecord.filter(queue="default").count() == 1

    run(body)


def test_earlier_queue_has_priority():
    async def body():
        q = Queue(name="high,default", timezone="UTC")
        await q.dispatch(Normal()); await q.dispatch(Normal()); await q.dispatch(High())
        while await q.run_next():
            pass
        assert CALLS == ["high", "default", "default"]

    run(body)


def test_cli_parse_queue():
    from forgeapi.cli.commands.queue_cmd import QueueCommand
    c = QueueCommand()
    assert c._parse_queue(["--queue=emails"]) == "emails"
    assert c._parse_queue(["--queue", "high,default"]) == "high,default"
    assert c._parse_queue([]) is None
    with pytest.raises(Exception):
        c._parse_queue(["--bogus"])
    with pytest.raises(Exception):
        c._parse_queue(["--queue="])
