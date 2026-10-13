from forgeapi.cli.commands.generate_cmd import MakeCommand
from forgeapi.cli.commands.generate_schema_cmd import GenerateSchemaCommand
from forgeapi.scheduling.scheduler import ScheduledJob

_make = MakeCommand()


# ── _to_snake ─────────────────────────────────────────────────────────────────

def test_to_snake_single():
    assert _make._to_snake("User") == "user"


def test_to_snake_camel():
    assert _make._to_snake("UserProfile") == "user_profile"


def test_to_snake_multi():
    assert _make._to_snake("AdminUserRole") == "admin_user_role"


def test_to_snake_already_lower():
    assert _make._to_snake("user") == "user"


# ── _to_plural ────────────────────────────────────────────────────────────────

def test_plural_regular():
    assert _make._to_plural("user") == "users"


def test_plural_y():
    assert _make._to_plural("category") == "categories"


def test_plural_s_suffix():
    assert _make._to_plural("address") == "addresses"


def test_plural_ch_suffix():
    assert _make._to_plural("branch") == "branches"


# ── _relative_import ──────────────────────────────────────────────────────────

def test_relative_same_package():
    assert _make._relative_import("app/controllers", "app/models") == "..models"


def test_relative_different_package():
    assert _make._relative_import("app/controllers", "database/models") == "database.models"


def test_relative_nested():
    assert _make._relative_import("app/controllers/admin", "app/models") == "...models"


def test_relative_same_dir():
    assert _make._relative_import("app/models", "app/schemas") == "..schemas"


# ── _parse_flags ──────────────────────────────────────────────────────────────

def test_parse_long_flags():
    flags, unknown = _make._parse_flags(["--model", "--schema"])
    assert flags["model"] is True
    assert flags["schema"] is True
    assert flags["controller"] is False
    assert unknown == []


def test_parse_short_flags():
    flags, unknown = _make._parse_flags(["-m", "-c"])
    assert flags["model"] is True
    assert flags["controller"] is True


def test_parse_compound_long():
    flags, unknown = _make._parse_flags(["--ms"])
    assert flags["model"] is True
    assert flags["schema"] is True
    assert flags["controller"] is False


def test_parse_compound_short():
    flags, unknown = _make._parse_flags(["-mcs"])
    assert flags["model"] is True
    assert flags["controller"] is True
    assert flags["schema"] is True


def test_parse_unknown_arg():
    flags, unknown = _make._parse_flags(["--unknown"])
    assert "--unknown" in unknown


def test_parse_empty():
    flags, unknown = _make._parse_flags([])
    assert all(not v for v in flags.values())
    assert unknown == []


def test_parse_controller_flag():
    flags, _ = _make._parse_flags(["--controller"])
    assert flags["controller"] is True


# ── _parse_namespace ──────────────────────────────────────────────────────────

def test_namespace_single_word():
    ns, resource = _make._parse_namespace("User")
    assert ns == ""
    assert resource == "User"


def test_namespace_two_words():
    ns, resource = _make._parse_namespace("AdminUser")
    assert ns == "admin"
    assert resource == "User"


def test_namespace_three_words():
    ns, resource = _make._parse_namespace("SuperAdminUser")
    assert ns == "super/admin"
    assert resource == "User"


def test_namespace_api_version():
    ns, resource = _make._parse_namespace("ApiV1User")
    assert ns == "api/v1"
    assert resource == "User"


# ── generate:schema flag parsing ──────────────────────────────────────────────

_gs = GenerateSchemaCommand()


def test_schema_flags_payload_only():
    want_p, want_r, crud, unknown = _gs._parse_flags(["--payload"])
    assert want_p is True
    assert want_r is False
    assert crud is None
    assert unknown == []


def test_schema_flags_response_only():
    want_p, want_r, crud, unknown = _gs._parse_flags(["--response"])
    assert want_p is False
    assert want_r is True


def test_schema_flags_both():
    want_p, want_r, crud, unknown = _gs._parse_flags(["--payload", "--response"])
    assert want_p is True
    assert want_r is True


def test_schema_flags_crud_long():
    _, _, crud, _ = _gs._parse_flags(["--payload", "--crud"])
    assert crud == {"c", "r", "u"}


def test_schema_flags_crud_short_all():
    _, _, crud, _ = _gs._parse_flags(["--payload", "-crud"])
    assert crud == {"c", "r", "u", "d"}


def test_schema_flags_crud_partial():
    _, _, crud, _ = _gs._parse_flags(["--payload", "--cu"])
    assert crud == {"c", "u"}


def test_schema_flags_unknown():
    _, _, _, unknown = _gs._parse_flags(["--payload", "--unknown"])
    assert "--unknown" in unknown


# ── ScheduledJob — compute_next_run ──────────────────────────────────────────

from datetime import datetime, timedelta


def _job(schedule_type, config) -> ScheduledJob:
    j = ScheduledJob(lambda: None, "test")
    j._schedule_type = schedule_type
    j._schedule_config = config
    return j


def test_interval_next_run():
    job = _job("interval", {"minutes": 30})
    now = datetime(2024, 1, 1, 12, 0, 0)
    nxt = job.compute_next_run(now)
    assert nxt == datetime(2024, 1, 1, 12, 30, 0)


def test_daily_next_run_future():
    job = _job("daily", {"hour": 9, "minute": 0})
    now = datetime(2024, 1, 1, 8, 0, 0)
    nxt = job.compute_next_run(now)
    assert nxt == datetime(2024, 1, 1, 9, 0, 0)


def test_daily_next_run_past_today():
    job = _job("daily", {"hour": 9, "minute": 0})
    now = datetime(2024, 1, 1, 10, 0, 0)
    nxt = job.compute_next_run(now)
    assert nxt == datetime(2024, 1, 2, 9, 0, 0)


def test_weekly_next_run():
    # next Monday from a Wednesday
    job = _job("weekly", {"weekday": 0, "hour": 3, "minute": 0})
    now = datetime(2024, 1, 3, 12, 0, 0)  # Wednesday
    nxt = job.compute_next_run(now)
    assert nxt.weekday() == 0
    assert nxt > now


def test_scheduler_registry():
    from forgeapi.scheduling.scheduler import Scheduler

    scheduler = Scheduler()
    scheduler.call(lambda: None).every(5).name("job-a")
    scheduler.call(lambda: None).daily_at("10:00").name("job-b")

    registry = scheduler.registry
    assert "job-a" in registry
    assert "job-b" in registry
    assert registry["job-a"]._schedule_config == {"minutes": 5}
    assert registry["job-b"]._schedule_config == {"hour": 10, "minute": 0}


# ── doctor ────────────────────────────────────────────────────────────────────

def _doctor_schedule(tmp_path, monkeypatch, body):
    from forgeapi.cli.commands.doctor_cmd import DoctorCommand
    from forgeapi.config import KitConfig

    f = tmp_path / "schedule.py"
    f.write_text(body)
    monkeypatch.chdir(tmp_path)
    doc = DoctorCommand()
    doc._check_scheduler(KitConfig())
    return doc.results


def test_doctor_schedule_valid(tmp_path, monkeypatch):
    res = _doctor_schedule(tmp_path, monkeypatch, (
        "from forgeapi import Scheduler\nscheduler = Scheduler()\n"
        "scheduler.call(lambda: None).cron('*/5 * * * *').name('a')\n"
    ))
    assert [r[0] for r in res] == ["ok"]


def test_doctor_schedule_missing_schedule_and_dupes(tmp_path, monkeypatch):
    res = _doctor_schedule(tmp_path, monkeypatch, (
        "from forgeapi import Scheduler\nscheduler = Scheduler()\n"
        "scheduler.call(lambda: None).name('a')\n"
        "scheduler.call(lambda: None).daily().name('b')\n"
        "scheduler.call(lambda: None).daily().name('b')\n"
    ))
    titles = " ".join(r[1] for r in res)
    assert all(r[0] == "fail" for r in res)
    assert "without a schedule: a" in titles and "duplicate job names: b" in titles


def test_doctor_schedule_no_scheduler_var(tmp_path, monkeypatch):
    res = _doctor_schedule(tmp_path, monkeypatch, "x = 1\n")
    assert res[0][0] == "fail"


def test_doctor_engine_detection():
    from forgeapi.cli.commands.doctor_cmd import DoctorCommand
    cfg = {"connections": {"default": {"engine": "tortoise.backends.mysql"}}}
    assert "mysql" in DoctorCommand._engine(cfg)
    assert "mysql" in DoctorCommand._engine({"connections": {"default": "MySQL://u@h/db"}})
    assert "mysql" not in DoctorCommand._engine({"connections": {"default": {"engine": "tortoise.backends.sqlite"}}})
