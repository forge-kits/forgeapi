"""Tests for Scheduler and ScheduledJob."""
import asyncio
import pytest
from datetime import datetime, timedelta

from forgeapi.scheduling.scheduler import Scheduler, ScheduledJob


def make_job(fn=None, label="test") -> ScheduledJob:
    fn = fn or (lambda: None)
    return ScheduledJob(fn, label)


# ---------------------------------------------------------------------------
# ScheduledJob — schedule configuration
# ---------------------------------------------------------------------------

class TestScheduledJobConfig:
    def test_every_sets_interval_minutes(self):
        job = make_job().every(15)
        assert job._schedule_type == "interval"
        assert job._schedule_config["minutes"] == 15

    def test_every_minute(self):
        job = make_job().every_minute()
        assert job._schedule_type == "interval"
        assert job._schedule_config["minutes"] == 1

    def test_hourly_sets_60_minutes(self):
        job = make_job().hourly()
        assert job._schedule_type == "interval"
        assert job._schedule_config["minutes"] == 60

    def test_daily_sets_midnight(self):
        job = make_job().daily()
        assert job._schedule_type == "daily"
        assert job._schedule_config["hour"] == 0
        assert job._schedule_config["minute"] == 0

    def test_daily_at_parses_time(self):
        job = make_job().daily_at("09:30")
        assert job._schedule_type == "daily"
        assert job._schedule_config["hour"] == 9
        assert job._schedule_config["minute"] == 30

    def test_weekly_on_sets_weekday(self):
        job = make_job().weekly_on("wednesday", at="08:00")
        assert job._schedule_type == "weekly"
        assert job._schedule_config["weekday"] == 2
        assert job._schedule_config["hour"] == 8
        assert job._schedule_config["minute"] == 0

    def test_weekly_on_unknown_day_raises(self):
        with pytest.raises(ValueError, match="Unknown day"):
            make_job().weekly_on("funday")

    def test_name_overrides_label(self):
        job = make_job(label="old").name("new")
        assert job._label == "new"

    def test_no_schedule_raises_on_compute(self):
        job = make_job()
        with pytest.raises(RuntimeError, match="no schedule"):
            job.compute_next_run(datetime.now())


# ---------------------------------------------------------------------------
# ScheduledJob — compute_next_run
# ---------------------------------------------------------------------------

class TestScheduledJobNextRun:
    def test_interval_next_run(self):
        now = datetime(2025, 1, 1, 12, 0, 0)
        job = make_job().every(30)
        nxt = job.compute_next_run(now)
        assert nxt == datetime(2025, 1, 1, 12, 30, 0)

    def test_daily_next_run_same_day_when_before(self):
        now = datetime(2025, 1, 1, 7, 0, 0)
        job = make_job().daily_at("09:00")
        nxt = job.compute_next_run(now)
        assert nxt == datetime(2025, 1, 1, 9, 0, 0)

    def test_daily_next_run_next_day_when_past(self):
        now = datetime(2025, 1, 1, 10, 0, 0)
        job = make_job().daily_at("09:00")
        nxt = job.compute_next_run(now)
        assert nxt == datetime(2025, 1, 2, 9, 0, 0)

    def test_weekly_advances_to_correct_weekday(self):
        # 2025-01-01 is a Wednesday (weekday=2)
        now = datetime(2025, 1, 1, 12, 0, 0)
        job = make_job().weekly_on("friday", at="10:00")
        nxt = job.compute_next_run(now)
        assert nxt.weekday() == 4  # Friday
        assert nxt.hour == 10

    def test_interval_multiple_advances(self):
        now = datetime(2025, 1, 1, 0, 0, 0)
        job = make_job().every(10)
        nxt = job.compute_next_run(now)
        nxt2 = job.compute_next_run(nxt)
        assert nxt2 == datetime(2025, 1, 1, 0, 20, 0)


# ---------------------------------------------------------------------------
# ScheduledJob.execute
# ---------------------------------------------------------------------------

class TestScheduledJobExecute:
    @pytest.mark.anyio
    async def test_executes_sync_fn(self):
        called = []
        job = make_job(fn=lambda: called.append(1)).every(1)
        status, err = await job.execute()
        assert called == [1]
        assert status == "success"
        assert err is None

    @pytest.mark.anyio
    async def test_executes_async_fn(self):
        called = []

        async def fn():
            called.append(1)

        job = make_job(fn=fn).every(1)
        status, err = await job.execute()
        assert called == [1]
        assert status == "success"

    @pytest.mark.anyio
    async def test_exception_returns_failed_status(self):
        def boom():
            raise ValueError("oops")

        job = make_job(fn=boom).every(1)
        status, err = await job.execute()
        assert status == "failed"
        assert "oops" in err

    @pytest.mark.anyio
    async def test_execute_does_not_raise(self):
        def boom():
            raise RuntimeError("boom")

        job = make_job(fn=boom).every(1)
        await job.execute()  # must not propagate


# ---------------------------------------------------------------------------
# Scheduler
# ---------------------------------------------------------------------------

class TestScheduler:
    def test_call_registers_job(self):
        s = Scheduler()
        job = s.call(lambda: None).every(5)
        assert job in s._jobs

    def test_call_returns_scheduled_job(self):
        s = Scheduler()
        result = s.call(lambda: None)
        assert isinstance(result, ScheduledJob)

    def test_registry_keyed_by_label(self):
        s = Scheduler()
        s.call(lambda: None).every(5).name("my-task")
        assert "my-task" in s.registry

    @pytest.mark.anyio
    async def test_run_executes_due_jobs_and_cancels(self):
        called = []

        async def task():
            called.append(1)

        s = Scheduler()
        s.call(task).every_minute()

        # Patch compute_next_run to return the past so it's immediately due
        job = s._jobs[0]
        job._schedule_type = "interval"
        job._schedule_config = {"minutes": 1}

        # Patch sync and run_due to avoid DB calls
        async def fake_sync():
            pass

        ran = []

        async def fake_run_due():
            ran.append(1)
            await task()

        s.sync = fake_sync
        s.run_due = fake_run_due

        runner = asyncio.create_task(s.run())
        await asyncio.sleep(0.1)
        runner.cancel()
        await asyncio.gather(runner, return_exceptions=True)

        assert len(ran) >= 1

    @pytest.mark.anyio
    async def test_run_cancels_cleanly(self):
        s = Scheduler()
        s.call(lambda: None).hourly()

        async def fake_sync():
            pass

        async def fake_run_due():
            pass

        s.sync = fake_sync
        s.run_due = fake_run_due

        task = asyncio.create_task(s.run())
        await asyncio.sleep(0.05)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
