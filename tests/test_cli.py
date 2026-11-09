import pytest
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


# ── make:job / policy / observer / provider ──────────────────────────────────

@pytest.fixture
def mk_project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "__init__.py").touch()
    return tmp_path


def _run_make(kind, name):
    MakeCommand().handle(f"make:{kind}", [name])


def test_make_job(mk_project):
    _run_make("job", "SendWelcomeEmail")
    src = (mk_project / "app/jobs/send_welcome_email.py").read_text()
    assert "class SendWelcomeEmail(Job):" in src
    assert (mk_project / "app/jobs/__init__.py").exists()
    compile(src, "job.py", "exec")


@pytest.mark.parametrize("name", ["Post", "PostPolicy"])
def test_make_policy_strips_suffix(mk_project, name):
    _run_make("policy", name)
    src = (mk_project / "app/policies/post_policy.py").read_text()
    assert "class PostPolicy(Policy):" in src and "@gate.policy(Post)" in src
    assert "from database.models import Post" in src
    assert not (mk_project / "app/policies/post_policy_policy.py").exists()
    compile(src, "policy.py", "exec")


def test_make_observer_and_provider(mk_project, capsys):
    _run_make("observer", "Post")
    _run_make("provider", "Metrics")
    obs = (mk_project / "app/observers/post_observer.py").read_text()
    prov = (mk_project / "app/providers/metrics_provider.py").read_text()
    assert "class PostObserver(ModelObserver):" in obs
    assert "from app.observers.post_observer import PostObserver" in obs
    assert "class MetricsProvider(Provider):" in prov
    assert "app.providers.metrics_provider.MetricsProvider" in capsys.readouterr().out
    compile(obs, "o.py", "exec"); compile(prov, "p.py", "exec")


def test_make_does_not_overwrite_and_validates_name(mk_project):
    _run_make("job", "Same")
    f = mk_project / "app/jobs/same.py"
    f.write_text("# edited\n")
    _run_make("job", "Same")
    assert f.read_text() == "# edited\n"
    with pytest.raises(Exception):
        _run_make("job", "1bad")


# ── unreachable database: one-line error, no traceback ───────────────────────

@pytest.fixture
def broken_db_project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.syspath_prepend(str(tmp_path))
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "database.py").write_text('config = {"tortoise_orm": "broken_orm_module.TORTOISE_ORM"}\n')
    (tmp_path / "broken_orm_module.py").write_text(
        "TORTOISE_ORM = {\n"
        '    "connections": {"default": {"engine": "tortoise.backends.sqlite",\n'
        '                                "credentials": {"file_path": "/nonexistent_dir_for_forgeapi_test/db.sqlite3"}}},\n'
        '    "apps": {"models": {"models": [], "default_connection": "default"}},\n'
        "}\n"
    )
    (tmp_path / "schedule.py").write_text(
        "from forgeapi import Scheduler\nscheduler = Scheduler()\nscheduler.call(lambda: None).daily().name('t')\n"
    )
    return tmp_path


@pytest.mark.parametrize("cmd", ["schedule:list", "schedule:run", "queue:run", "queue:work"])
def test_unreachable_database_gives_readable_error(broken_db_project, capsys, cmd):
    import typer
    from forgeapi.cli.commands.queue_cmd import QueueCommand
    from forgeapi.cli.commands.schedule_cmd import ScheduleCommand

    command = ScheduleCommand() if cmd.startswith("schedule") else QueueCommand()
    with pytest.raises(typer.Exit) as info:
        command.handle(cmd, [])
    err = capsys.readouterr().err
    assert info.value.exit_code == 1
    first_line = err.strip().splitlines()[0]
    assert "ERROR" in first_line and "Cannot connect to the database" in first_line
    assert "Hint:" in err and "forgeapi doctor" in err
    assert "Traceback" not in err


def test_connect_database_chains_original_error(broken_db_project):
    import asyncio
    from forgeapi.cli.base import Command
    from forgeapi.exceptions import ForgeAPIError

    cfg = {
        "connections": {"default": {"engine": "tortoise.backends.sqlite",
                                    "credentials": {"file_path": "/nonexistent_dir_for_forgeapi_test/db.sqlite3"}}},
        "apps": {"models": {"models": [], "default_connection": "default"}},
    }
    with pytest.raises(ForgeAPIError) as info:
        asyncio.run(Command.connect_database(cfg))
    assert info.value.__cause__ is not None   # `from exc`: the real reason is kept


# ── db:fresh / db:migrate --force ────────────────────────────────────────────

@pytest.fixture
def sqlite_orm(tmp_path):
    """A SQLite file with a model-less table, a many-to-many-style table and migration history."""
    import sqlite3

    db = tmp_path / "t.sqlite3"
    conn = sqlite3.connect(db)
    conn.executescript(
        "CREATE TABLE users (id INTEGER PRIMARY KEY);"
        "CREATE TABLE posts (id INTEGER PRIMARY KEY, user_id INTEGER REFERENCES users(id));"
        "CREATE TABLE post_tags (post_id INTEGER REFERENCES posts(id));"
        "CREATE TABLE tortoise_migrations (app TEXT, name TEXT);"
        "INSERT INTO users VALUES (1); INSERT INTO posts VALUES (1, 1); INSERT INTO post_tags VALUES (1);"
        "INSERT INTO tortoise_migrations VALUES ('models', '0001_initial');"
    )
    conn.commit(); conn.close()
    config = {
        "connections": {"default": {"engine": "tortoise.backends.sqlite", "credentials": {"file_path": str(db)}}},
        "apps": {"models": {"models": ["forgeapi.queue.models"], "default_connection": "default"}},
    }
    return db, config


def _tables(db):
    import sqlite3
    conn = sqlite3.connect(db)
    try:
        return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        conn.close()


def test_fresh_drop_removes_every_table_and_history(sqlite_orm):
    import asyncio
    from forgeapi.cli.commands.fresh_cmd import FreshCommand, _DROP_SQL

    db, config = sqlite_orm
    done, failed = asyncio.run(FreshCommand()._apply(config, _DROP_SQL, include_history=True))
    assert failed == []
    assert set(done) == {"users", "posts", "post_tags", "tortoise_migrations"}
    assert _tables(db) - {"sqlite_sequence"} == set()


def test_fresh_truncate_keeps_history(sqlite_orm):
    import asyncio
    import sqlite3
    from forgeapi.cli.commands.fresh_cmd import FreshCommand, _TRUNCATE_SQL

    db, config = sqlite_orm
    done, failed = asyncio.run(FreshCommand()._apply(config, _TRUNCATE_SQL, include_history=False))
    assert failed == [] and "tortoise_migrations" not in done
    conn = sqlite3.connect(db)
    assert conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM tortoise_migrations").fetchone()[0] == 1
    conn.close()


def _force_project(monkeypatch, calls):
    from forgeapi.cli.commands import db_cmd, fresh_cmd

    class Cfg:
        class database:
            tortoise_orm = "x.TORTOISE_ORM"

    monkeypatch.setattr("forgeapi.config.load_config", lambda: Cfg)
    monkeypatch.setattr(db_cmd.DbCommand, "_find_tortoise_bin", staticmethod(lambda: "tortoise"))
    monkeypatch.setattr(
        fresh_cmd.FreshCommand, "drop_everything",
        lambda self, *, assume_yes=False: calls.append(("drop", assume_yes)),
    )

    class Result:
        returncode = 0

    monkeypatch.setattr(db_cmd.subprocess, "run", lambda command, env=None: calls.append(("run", command)) or Result)


def test_migrate_force_drops_then_runs_migrate_without_force_flags(monkeypatch):
    from forgeapi.cli.commands.db_cmd import DbCommand

    calls = []
    _force_project(monkeypatch, calls)
    with pytest.raises(SystemExit) as info:
        DbCommand().handle("db:migrate", ["--force", "-y"])
    assert info.value.code == 0
    assert calls == [("drop", True), ("run", ["tortoise", "-c", "x.TORTOISE_ORM", "migrate"])]


@pytest.mark.parametrize("flag", ["--dry-run", "--fake"])
def test_migrate_force_rejects_dry_run_and_fake(monkeypatch, flag):
    import typer
    from forgeapi.cli.commands.db_cmd import DbCommand

    calls = []
    _force_project(monkeypatch, calls)
    with pytest.raises(typer.Exit):
        DbCommand().handle("db:migrate", ["--force", flag])
    assert calls == []   # nothing was dropped


def test_migrate_without_force_does_not_drop(monkeypatch):
    from forgeapi.cli.commands.db_cmd import DbCommand

    calls = []
    _force_project(monkeypatch, calls)
    with pytest.raises(SystemExit):
        DbCommand().handle("db:migrate", [])
    assert [c[0] for c in calls] == ["run"]


# ── ui ───────────────────────────────────────────────────────────────────────

def test_help_lists_every_registered_group(capsys):
    from forgeapi.cli.main import _COMMAND_GROUPS, _show_help

    _show_help()
    out = capsys.readouterr().out
    assert "ForgeAPI" in out
    assert "███████╗" in out                      # the big logo lives only in the command list
    for _, rows in _COMMAND_GROUPS:
        for usage, _ in rows:
            assert usage.split(" ")[0] in out
    assert "db:migrate" in out and "--force" in out
    assert "\x1b[" not in out                    # no colour codes when not a terminal


def test_help_commands_all_resolve_to_a_command():
    from forgeapi.cli.main import _COMMAND_GROUPS, _registry

    for _, rows in _COMMAND_GROUPS:
        for usage, _ in rows:
            assert _registry.find(usage.split(" ")[0]) is not None, usage


def test_unknown_command_is_an_error(capsys):
    import typer
    from typer.testing import CliRunner
    from forgeapi.cli.main import app

    result = CliRunner().invoke(app, ["nope"])
    assert result.exit_code == 1
    assert "not defined" in result.output


def test_ui_leader_fills_width(capsys):
    from forgeapi.cli import ui

    ui.leader("users", "DONE")
    line = capsys.readouterr().out.rstrip()
    assert line.startswith("  users ...") and line.endswith("DONE")
    assert len(line) <= ui.console.width


def test_runserver_shows_url_without_logo(monkeypatch, capsys):
    import sys
    import types
    from forgeapi.cli.commands.runserver_cmd import RunserverCommand

    started = {}
    fake = types.SimpleNamespace(run=lambda app, **kw: started.update(app=app, **kw))
    monkeypatch.setitem(sys.modules, "uvicorn", fake)
    RunserverCommand().handle("runserver", ["--port", "9000", "--reload"])
    out = capsys.readouterr().out
    assert "███████╗" not in out
    assert "http://127.0.0.1:9000" in out
    assert started == {"app": "main:app", "host": "127.0.0.1", "port": 9000, "reload": True}


# ── help texts and bare group commands ───────────────────────────────────────

@pytest.mark.parametrize("group", ["db", "schedule", "queue", "mcp", "make"])
def test_bare_group_command_shows_styled_help(group, capsys):
    from forgeapi.cli.main import _registry

    _registry.find(group).handle(group, [])
    out = capsys.readouterr().out
    assert " Usage:" in out
    assert "Traceback" not in out and "ERROR" not in out


def test_help_renderer_keeps_text_and_adds_no_codes_off_tty(capsys):
    from forgeapi.cli import ui

    ui.render_help("Usage: forgeapi x <a>\n\nOptions:\n  --go   Do it   # note\n\nExamples:\n  forgeapi x 1\n")
    out = capsys.readouterr().out
    assert "Usage: forgeapi x <a>" in out and "--go" in out and "Do it" in out and "forgeapi x 1" in out
    assert "\x1b[" not in out


def test_help_renderer_styles_by_role():
    from forgeapi.cli.ui import _help_line

    assert _help_line("Usage: forgeapi db:<sub>").plain == " Usage: forgeapi db:<sub>"
    heading = _help_line("Options:")
    assert heading.plain == " Options:" and heading.style == "bold yellow"
    row = _help_line("  --force   Drop it")
    assert [s.style for s in row.spans] == ["green"] and row.plain[row.spans[0].start:row.spans[0].end] == "--force"
    example = _help_line("  forgeapi make:job X   # → file")
    assert [s.style for s in example.spans] == ["green", "dim"]


def test_mcp_status_renders_connected_line(monkeypatch, capsys):
    import subprocess
    import types
    from forgeapi.cli.commands import mcp_cmd

    monkeypatch.setattr(mcp_cmd.shutil, "which", lambda name: "/bin/claude")
    out_text = "Checking...\nforge-kits: /x/y/forgeapi-mcp  - ✔ Connected\nother: foo - ✗ Failed to connect\n"
    monkeypatch.setattr(
        mcp_cmd.subprocess, "run",
        lambda *a, **k: types.SimpleNamespace(stdout=out_text, returncode=0),
    )
    mcp_cmd.McpCommand()._status(__import__("typer"))
    out = capsys.readouterr().out
    assert "forge-kits ..." in out and "CONNECTED" in out
    assert "/x/y/forgeapi-mcp" in out
    assert "other" not in out        # only the forge-kits server is reported


# ── project guard: file-writing commands never guess a location ──────────────

def test_find_project_root_walks_up(tmp_path):
    from forgeapi.support.project import find_project_root

    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "project.py").write_text("config = {}\n")
    deep = tmp_path / "app" / "x"
    deep.mkdir(parents=True)
    assert find_project_root(deep) == tmp_path.resolve()
    assert find_project_root(tmp_path) == tmp_path.resolve()


def test_find_project_root_ignores_unrelated_config_dir(tmp_path):
    from forgeapi.support.project import find_project_root

    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "settings.ini").write_text("x")
    assert find_project_root(tmp_path) is None


def test_make_outside_project_writes_nothing(tmp_path, monkeypatch):
    from typer.testing import CliRunner
    from forgeapi.cli.main import app

    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(app, ["make:job", "SendX"])
    assert result.exit_code == 1
    assert "No ForgeAPI project found" in result.output and "forgeapi init" in result.output
    assert list(tmp_path.iterdir()) == []


def test_make_in_project_subdirectory_uses_project_root(tmp_path, monkeypatch):
    from typer.testing import CliRunner
    from forgeapi.cli.main import app

    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "project.py").write_text("config = {}\n")
    sub = tmp_path / "app" / "deep"
    sub.mkdir(parents=True)
    monkeypatch.chdir(sub)
    result = CliRunner().invoke(app, ["make:job", "Deep"])
    assert result.exit_code == 0, result.output
    assert (tmp_path / "app" / "jobs" / "deep.py").exists()
    assert list(sub.iterdir()) == []                 # nothing created next to the caller


@pytest.mark.parametrize("args", [["make"], ["db"], ["queue"], ["make:job", "-h"], ["mcp"]])
def test_commands_that_need_no_project_run_anywhere(tmp_path, monkeypatch, args):
    from typer.testing import CliRunner
    from forgeapi.cli.main import app

    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(app, args)
    assert "No ForgeAPI project found" not in result.output
    assert result.exit_code == 0, result.output


def test_doctor_is_not_blocked_outside_a_project(tmp_path, monkeypatch):
    from typer.testing import CliRunner
    from forgeapi.cli.main import app

    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(app, ["doctor", "--no-db"])
    assert "No ForgeAPI project found" not in result.output
    assert "config/ directory not found" in result.output     # it reports the problem instead


# ── forgeapi init: default User model + initial migration ──────────────────────

def _init_project(tmp_path, monkeypatch, strategy: str, driver: str = "aiosqlite"):
    from forgeapi.cli import ui
    from forgeapi.cli.commands.init_cmd import InitCommand

    answers = iter([strategy, driver])
    monkeypatch.setattr(ui, "choose", lambda *a, **kw: next(answers))
    monkeypatch.chdir(tmp_path)
    InitCommand().handle("init", ["demo"])
    return tmp_path / "demo"


@pytest.mark.parametrize("strategy", ["cookie", "telegram"])
def test_init_creates_user_model_and_guard_points_to_it(tmp_path, monkeypatch, strategy):
    root = _init_project(tmp_path, monkeypatch, strategy)
    src = (root / "database/models/user.py").read_text()
    expected = {
        "cookie": ("id", "name", "email", "password", "created_at", "updated_at"),
        "telegram": ("id", "username", "first_name", "last_name", "photo_url",
                     "language_code", "created_at", "updated_at"),
    }[strategy]
    for field in expected:
        assert f"    {field} = fields." in src
    if strategy == "telegram":
        assert "password" not in src and "email" not in src
    assert "from .user import User" in (root / "database/models/__init__.py").read_text()
    assert '"model": "database.models.user.User"' in (root / "config/auth.py").read_text()


def test_init_generates_initial_migration(tmp_path, monkeypatch):
    from forgeapi.cli.commands.db_cmd import DbCommand

    if DbCommand._find_tortoise_bin() is None:
        pytest.skip("tortoise binary not available")
    root = _init_project(tmp_path, monkeypatch, "cookie")
    migrations = sorted((root / "database/migrations").glob("0001_*.py"))
    assert len(migrations) == 1
    body = migrations[0].read_text()
    for table in ("users", "queued_jobs", "failed_jobs", "scheduled_tasks"):
        assert f"'table': '{table}'" in body


# ── make:command + project commands ───────────────────────────────────────────

@pytest.mark.parametrize("name, expected", [
    ("SendWeeklyReport", "send:weekly-report"),
    ("SendSMS", "send:sms"),
    ("Cleanup", "cleanup"),
])
def test_command_name_from_class(name, expected):
    assert _make._command_name(name) == expected


def test_make_command(cmd_project):
    _run_make("command", "SendWeeklyReport")
    f = cmd_project / "app/commands/send_weekly_report_command.py"
    src = f.read_text()
    assert "class SendWeeklyReportCommand(Command):" in src
    assert 'name = "send:weekly-report"' in src
    assert (cmd_project / "app/commands/__init__.py").exists()
    compile(src, "command.py", "exec")


def test_make_command_strips_suffix(cmd_project):
    _run_make("command", "SendReportCommand")
    src = (cmd_project / "app/commands/send_report_command.py").read_text()
    assert "class SendReportCommand(Command):" in src and 'name = "send:report"' in src
    assert not (cmd_project / "app/commands/send_report_command_command.py").exists()


def test_make_command_refuses_builtin_name(cmd_project):
    from typer import Exit

    with pytest.raises((Exit, SystemExit)):
        _run_make("command", "MakeThing")                 # make:thing is a built-in prefix
    assert not (cmd_project / "app/commands").exists()


def test_generated_command_is_discovered_and_runs(cmd_project):
    from typer.testing import CliRunner
    from forgeapi.cli.main import app

    _run_make("command", "SendWeeklyReport")
    runner = CliRunner()
    result = runner.invoke(app, ["send:weekly-report"])
    assert result.exit_code == 0, result.output
    assert "send:weekly-report ran." in result.output

    listing = runner.invoke(app, [])
    assert "send:weekly-report" in listing.output and "project" in listing.output


def test_project_command_receives_args_and_help(cmd_project):
    from typer.testing import CliRunner
    from forgeapi.cli.main import app

    (cmd_project / "app/commands").mkdir()
    (cmd_project / "app/commands/__init__.py").touch()
    (cmd_project / "app/commands/greet_command.py").write_text(
        "from forgeapi.cli import ui\n"
        "from forgeapi.cli.base import Command\n\n"
        "class GreetCommand(Command):\n"
        "    name = 'greet'\n"
        "    help_text = 'Usage: forgeapi greet <who>\\n'\n"
        "    def handle(self, cmd, args):\n"
        "        ui.info('hello ' + ' '.join(args))\n"
    )
    runner = CliRunner()
    assert "hello world" in runner.invoke(app, ["greet", "world"]).output
    assert "forgeapi greet <who>" in runner.invoke(app, ["greet", "-h"]).output


def test_broken_and_conflicting_project_commands(cmd_project):
    from typer.testing import CliRunner
    from forgeapi.cli.main import app

    d = cmd_project / "app/commands"
    d.mkdir()
    (d / "__init__.py").touch()
    (d / "broken.py").write_text("raise RuntimeError('boom')\n")
    (d / "clash.py").write_text(
        "from forgeapi.cli.base import Command\n\n"
        "class Clash(Command):\n"
        "    name = 'db:migrate'\n"
        "    def handle(self, cmd, args):\n"
        "        raise AssertionError('must never shadow a built-in')\n"
    )
    (d / "fine.py").write_text(
        "from forgeapi.cli.base import Command\n\n"
        "class Fine(Command):\n"
        "    name = 'fine'\n"
        "    def handle(self, cmd, args):\n"
        "        print('fine ran')\n"
    )
    runner = CliRunner()
    ok = runner.invoke(app, ["fine"])
    assert ok.exit_code == 0 and "fine ran" in ok.output          # the broken file did not hide it

    missing = runner.invoke(app, ["nope"])
    assert missing.exit_code == 1
    assert "boom" in missing.output and "already taken" in missing.output


def test_unknown_command_outside_project_is_still_an_error(tmp_path, monkeypatch):
    from typer.testing import CliRunner
    from forgeapi.cli.main import app

    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(app, ["nope"])
    assert result.exit_code == 1 and "is not defined" in result.output
