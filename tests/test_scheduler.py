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


class TestMonthlyYearly:
    def test_monthly_clamps_to_last_day(self):
        job = make_job().monthly_on(31, at="02:00")
        assert job.compute_next_run(datetime(2025, 1, 31, 3, 0)) == datetime(2025, 2, 28, 2, 0)

    def test_monthly_this_month_if_not_passed(self):
        job = make_job().monthly_on(15)
        assert job.compute_next_run(datetime(2025, 3, 1)) == datetime(2025, 3, 15)

    def test_monthly_december_rolls_year(self):
        job = make_job().monthly()
        assert job.compute_next_run(datetime(2025, 12, 1, 1, 0)) == datetime(2026, 1, 1)

    def test_yearly(self):
        job = make_job().yearly_on(6, 1, at="09:00")
        assert job.compute_next_run(datetime(2025, 7, 1)) == datetime(2026, 6, 1, 9, 0)

    def test_every_two_years(self):
        job = make_job().every_two_years(1, 1)
        assert job.compute_next_run(datetime(2025, 1, 1, 0, 1)) == datetime(2027, 1, 1)

    def test_leap_day_falls_back(self):
        job = make_job().yearly_on(2, 29)
        assert job.compute_next_run(datetime(2024, 3, 1)) == datetime(2025, 2, 28)

    def test_invalid_values(self):
        with pytest.raises(ValueError):
            make_job().monthly_on(32)
        with pytest.raises(ValueError):
            make_job().yearly_on(13, 1)


class TestCron:
    def test_every_five_minutes(self):
        job = make_job().cron("*/5 * * * *")
        assert job.compute_next_run(datetime(2025, 1, 1, 10, 3, 30)) == datetime(2025, 1, 1, 10, 5)
        assert job.compute_next_run(datetime(2025, 1, 1, 10, 5)) == datetime(2025, 1, 1, 10, 10)

    def test_weekdays_at_nine(self):
        job = make_job().cron("0 9 * * mon-fri")
        # Friday 2025-01-03 10:00 -> Monday 2025-01-06 09:00
        assert job.compute_next_run(datetime(2025, 1, 3, 10, 0)) == datetime(2025, 1, 6, 9, 0)

    def test_sunday_zero_and_seven(self):
        for expr in ("0 0 * * 0", "0 0 * * 7"):
            nxt = make_job().cron(expr).compute_next_run(datetime(2025, 1, 1))
            assert nxt == datetime(2025, 1, 5)  # Sunday

    def test_month_rollover_and_list(self):
        job = make_job().cron("30 6 1,15 * *")
        assert job.compute_next_run(datetime(2025, 12, 15, 7, 0)) == datetime(2026, 1, 1, 6, 30)

    def test_dom_or_dow_when_both_restricted(self):
        job = make_job().cron("0 0 13 * fri")
        assert job.compute_next_run(datetime(2025, 1, 1)) == datetime(2025, 1, 3)  # Friday

    def test_leap_day(self):
        job = make_job().cron("0 0 29 2 *")
        assert job.compute_next_run(datetime(2025, 1, 1)) == datetime(2028, 2, 29)

    @pytest.mark.parametrize("bad", ["* * * *", "60 * * * *", "*/0 * * * *", "a * * * *", "5-1 * * * *"])
    def test_invalid(self, bad):
        with pytest.raises(ValueError):
            make_job().cron(bad)


class TestTimezone:
    def test_now_uses_configured_timezone(self):
        from datetime import timezone as _tz
        s = Scheduler(timezone="Asia/Tokyo")
        diff = s.now() - datetime.now(_tz.utc).replace(tzinfo=None)
        assert timedelta(hours=8, minutes=59) < diff < timedelta(hours=9, minutes=1)
        assert s.now().tzinfo is None

    def test_default_uses_project_config(self, monkeypatch, tmp_path):
        (tmp_path / "config").mkdir()
        (tmp_path / "config" / "project.py").write_text('config = {"timezone": "Asia/Tokyo"}\n')
        monkeypatch.chdir(tmp_path)
        assert Scheduler().timezone == "Asia/Tokyo"

    def test_no_config_means_local(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        assert Scheduler().timezone is None

    def test_invalid_timezone_in_config(self):
        from forgeapi.config import config_from_dict
        from forgeapi.exceptions import ForgeAPIConfigError
        with pytest.raises(ForgeAPIConfigError):
            config_from_dict({"project": {"timezone": "Mars/Base"}})
        assert config_from_dict({"project": {"timezone": "Europe/Sofia"}}).project.timezone == "Europe/Sofia"


class TestQueueTimezone:
    def test_queue_now_uses_timezone(self):
        from datetime import timezone as _tz
        from forgeapi.queue.queue import Queue
        diff = Queue(timezone="Asia/Tokyo").now() - datetime.now(_tz.utc).replace(tzinfo=None)
        assert timedelta(hours=8, minutes=59) < diff < timedelta(hours=9, minutes=1)

    def test_queue_default_reads_project_config(self, monkeypatch, tmp_path):
        from forgeapi.queue.queue import Queue
        (tmp_path / "config").mkdir()
        (tmp_path / "config" / "project.py").write_text('config = {"timezone": "Asia/Tokyo"}\n')
        monkeypatch.chdir(tmp_path)
        assert Queue().timezone == "Asia/Tokyo"


class TestNaiveWall:
    def test_naive_unchanged(self):
        from forgeapi.support.clock import naive_wall
        d = datetime(2025, 1, 1, 9, 0)
        assert naive_wall(d) == d

    def test_aware_converted_to_utc_wall(self):
        from datetime import timezone as _tz
        from forgeapi.support.clock import naive_wall
        import zoneinfo
        d = datetime(2025, 1, 1, 12, 0, tzinfo=zoneinfo.ZoneInfo("Europe/Sofia"))  # 10:00 UTC
        assert naive_wall(d) == datetime(2025, 1, 1, 10, 0)
        assert naive_wall(datetime(2025, 1, 1, 9, 0, tzinfo=_tz.utc)) == datetime(2025, 1, 1, 9, 0)


class TestWithoutOverlapping:
    def test_flag_and_validation(self):
        assert make_job().without_overlapping()._overlap_ttl == 1440
        assert make_job().without_overlapping(expires_after=5)._overlap_ttl == 5
        assert make_job()._overlap_ttl is None
        with pytest.raises(ValueError):
            make_job().without_overlapping(expires_after=0)

    def test_skips_while_running_then_releases(self):
        from tortoise import Tortoise
        import tortoise.timezone as tt
        from forgeapi.scheduling.models import ScheduledTask
        from forgeapi.support.clock import to_db

        async def scenario():
            await Tortoise.init(config={
                "connections": {"default": "sqlite://:memory:"},
                "apps": {"models": {"models": ["forgeapi.scheduling.models"], "default_connection": "default"}},
            })
            await Tortoise.generate_schemas()
            try:
                runs, gate = [], asyncio.Event()

                async def slow():
                    runs.append(1)
                    await gate.wait()

                s = Scheduler(timezone="UTC")
                s.call(slow).every_minute().without_overlapping().name("slow")
                await s.sync()

                async def make_due():
                    await ScheduledTask.filter(name="slow").update(
                        next_run_at=to_db(s.now() - timedelta(seconds=5)))

                await make_due()
                first = asyncio.create_task(s.run_due())
                await asyncio.sleep(0.1)
                await make_due()
                assert await s.run_due() == 0           # slot skipped while running
                with pytest.raises(ValueError, match="already running"):
                    await s.run_one("slow")
                gate.set()
                assert await first == 1
                assert (await ScheduledTask.get(name="slow")).running_since is None
                await make_due()
                assert await s.run_due() == 1           # lock released -> runs again
                assert len(runs) == 2
            finally:
                await Tortoise.close_connections()
                tt._reset_timezone_cache()

        asyncio.run(scenario())

    def test_expired_lock_is_ignored(self):
        job = make_job().without_overlapping(expires_after=10)

        class R:
            running_since = datetime(2025, 1, 1, 10, 0)

        s = Scheduler(timezone="UTC")
        assert s._is_locked(R, job, datetime(2025, 1, 1, 10, 5)) is True
        assert s._is_locked(R, job, datetime(2025, 1, 1, 10, 11)) is False
