"""`forgeapi runserver` in the dev interface: the multiplexer, the process plan and the in-app worker switch."""
import asyncio
import sys
import time

import pytest

from forgeapi.cli.commands.runserver_cmd import plan_processes
from forgeapi.cli.multiplex import Multiplexer, Proc
from forgeapi.config.models import KitConfig
from forgeapi.support.workers import EXTERNAL_WORKERS_ENV, workers_run_externally

PY = sys.executable


def _py(code: str) -> list[str]:
    return [PY, "-c", code]


async def _run(procs, **kw):
    lines = []
    code = await Multiplexer(procs, lambda n, line, k: lines.append((n, k, line)), grace=2, **kw).run()
    return code, lines


async def test_output_is_prefixed_per_process_and_critical_exit_stops_the_rest():
    start = time.monotonic()
    code, lines = await _run([
        Proc("server", _py("import time; print('hello', flush=True); time.sleep(1.5)"), critical=True),
        Proc("queue", _py("import time; print('up', flush=True); time.sleep(60)")),
    ])
    assert code == 0
    assert ("server", "out", "hello") in lines and ("queue", "out", "up") in lines
    assert ("server", "status", "exited with code 0") in lines
    assert ("queue", "status", "stopped") in lines
    assert time.monotonic() - start < 15          # the sleeping worker was stopped, not waited for


async def test_exit_code_of_the_critical_process_is_returned():
    code, lines = await _run([Proc("server", _py("import sys; print('boom'); sys.exit(3)"), critical=True)])
    assert code == 3
    assert ("server", "status", "exited with code 3") in lines


async def test_a_worker_that_exits_does_not_stop_the_others():
    code, lines = await _run([
        Proc("server", _py("import time; time.sleep(1.5); print('still here')"), critical=True),
        Proc("queue", _py("import sys; print('crash'); sys.exit(1)")),
    ], auto_restart=False)
    assert ("queue", "status", "exited with code 1") in lines
    assert ("server", "out", "still here") in lines and code == 0


async def test_processes_start_one_after_another_when_ready_markers_are_given():
    order = []
    server = Proc("server", _py("import time; time.sleep(0.6); print('READY-S', flush=True); time.sleep(1.5)"),
                  critical=True, ready="READY-S")
    queue = Proc("queue", _py("print('queue started', flush=True)"))
    lines = []

    def emit(name, line, kind):
        lines.append((name, line))

    await Multiplexer([server, queue], emit, grace=2, auto_restart=False).run()
    names = [n for n, line in lines if line in ("READY-S", "queue started")]
    assert names == ["server", "queue"]            # the queue printed only after the server was ready


async def test_ready_marker_is_found_in_coloured_output():
    server = Proc("server", _py("import time; print('\\x1b[32mApplication startup complete\\x1b[0m', flush=True); time.sleep(1.5)"),
                  critical=True, ready="Application startup complete")
    code, lines = await _run([server, Proc("queue", _py("print('go')"))])
    assert ("queue", "out", "go") in lines


async def test_a_process_that_never_gets_ready_does_not_block_forever():
    slow = Proc("server", _py("import time; time.sleep(30)"), critical=True, ready="never printed")
    other = Proc("queue", _py("print('go', flush=True)"))
    lines = []
    mux = Multiplexer([slow, other], lambda n, line, k: lines.append((n, k, line)), grace=1, ready_timeout=0.5)
    task = asyncio.create_task(mux.run())
    await asyncio.sleep(2)
    assert ("queue", "out", "go") in lines
    assert any("not ready" in line for _, k, line in lines if k == "status")
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


async def test_cancelling_stops_every_child():
    lines = []
    mux = Multiplexer([
        Proc("server", _py("import time; print('s', flush=True); time.sleep(60)"), critical=True),
        Proc("queue", _py("import time; print('q', flush=True); time.sleep(60)")),
    ], lambda n, line, k: lines.append((n, k, line)), grace=2)
    task = asyncio.create_task(mux.run())
    await asyncio.sleep(1.5)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert ("server", "status", "stopped") in lines and ("queue", "status", "stopped") in lines


# ── plan ─────────────────────────────────────────────────────────────────────

def _cfg(provided=(), **sections):
    cfg = KitConfig(**sections)
    cfg._provided = set(provided)
    return cfg


def _plan(cfg, **kw):
    return plan_processes(cfg, app_path="main:app", host="127.0.0.1", port=8000, reload=kw.get("reload", True))


def test_plan_with_nothing_configured_is_just_the_server():
    procs = _plan(_cfg())
    assert [p.name for p in procs] == ["server"]
    assert procs[0].critical and EXTERNAL_WORKERS_ENV not in procs[0].env
    assert "--reload" in procs[0].argv and "main:app" in procs[0].argv


def test_plan_adds_queue_worker_and_disables_the_embedded_one(monkeypatch):
    procs = _plan(_cfg(provided={"queue"}))
    assert [p.name for p in procs] == ["server", "queue"]
    assert procs[0].env[EXTERNAL_WORKERS_ENV] == "1"
    assert procs[1].argv[-1] == "queue:work" and not procs[1].critical


def test_plan_has_no_workers_without_their_config_files():
    assert [p.name for p in _plan(_cfg(provided=set()))] == ["server"]


def test_plan_scheduler_needs_its_schedule_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cfg = _cfg(provided={"scheduler"}, scheduler={"schedule": "schedule.py"})
    assert [p.name for p in _plan(cfg)] == ["server"]
    (tmp_path / "schedule.py").write_text("x = 1\n")
    procs = _plan(cfg)
    assert [p.name for p in procs] == ["server", "schedule"] and procs[1].argv[-1] == "schedule:work"


def test_plan_order_is_server_queue_schedule(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "schedule.py").write_text("x = 1\n")
    cfg = _cfg(provided={"queue", "scheduler"}, queue={}, scheduler={})
    assert [p.name for p in _plan(cfg)] == ["server", "queue", "schedule"]


def test_plan_without_reload():
    assert "--reload" not in _plan(_cfg(), reload=False)[0].argv


# ── in-app workers switch off ────────────────────────────────────────────────

@pytest.mark.parametrize("value,expected", [("1", True), ("true", True), ("YES", True), ("0", False), ("", False)])
def test_external_workers_flag(monkeypatch, value, expected):
    monkeypatch.setenv(EXTERNAL_WORKERS_ENV, value)
    assert workers_run_externally() is expected


def test_embedded_workers_are_not_started_when_external(monkeypatch, tmp_path):
    from fastapi import FastAPI

    from forgeapi.queue.provider import QueueProvider
    from forgeapi.scheduling.provider import SchedulerProvider

    monkeypatch.chdir(tmp_path)
    (tmp_path / "schedule.py").write_text("from forgeapi import Scheduler\nscheduler = Scheduler()\n")
    cfg = _cfg(provided={"queue", "scheduler"})

    def hooks(provider_cls):
        app = FastAPI()
        provider_cls(app, cfg).boot()
        return len(app.router.on_startup)

    monkeypatch.delenv(EXTERNAL_WORKERS_ENV, raising=False)
    assert hooks(QueueProvider) == 1 and hooks(SchedulerProvider) == 1
    monkeypatch.setenv(EXTERNAL_WORKERS_ENV, "1")
    assert hooks(QueueProvider) == 0 and hooks(SchedulerProvider) == 0


def test_schedule_command_reads_the_file_from_the_scheduler_config(tmp_path, monkeypatch):
    from forgeapi.cli.commands.schedule_cmd import ScheduleCommand

    monkeypatch.chdir(tmp_path)
    (tmp_path / "config").mkdir()
    (tmp_path / "config/scheduler.py").write_text("config = {'schedule': 'jobs/plan.py'}\n")
    (tmp_path / "jobs").mkdir()
    (tmp_path / "jobs/plan.py").write_text("from forgeapi import Scheduler\nscheduler = Scheduler()\n")
    scheduler, cfg = ScheduleCommand()._load()
    assert cfg.scheduler.schedule == "jobs/plan.py" and scheduler is not None


# ── restart and states ───────────────────────────────────────────────────────

def _start(procs, **kw):
    lines, states = [], []
    mux = Multiplexer(procs, lambda n, line, k: lines.append((n, k, line)), on_state=lambda n, st: states.append((n, st)),
                      grace=2, backoff=0.05, **kw)
    return mux, asyncio.create_task(mux.run()), lines, states


async def _until(predicate, timeout=10.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if predicate():
            return True
        await asyncio.sleep(0.05)
    return False


async def test_a_crashed_worker_is_restarted_automatically():
    mux, task, lines, _ = _start([
        Proc("server", _py("import time; time.sleep(30)"), critical=True),
        Proc("queue", _py("import sys; print('boot', flush=True); sys.exit(1)")),
    ], max_crashes=50)
    assert await _until(lambda: sum(1 for n, k, line in lines if (n, line) == ("queue", "boot")) >= 3)
    assert any("restarting in" in line for _, k, line in lines if k == "status")
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


async def test_a_worker_that_keeps_crashing_is_given_up():
    mux, task, lines, states = _start([
        Proc("server", _py("import time; time.sleep(30)"), critical=True),
        Proc("queue", _py("import sys; sys.exit(2)")),
    ], max_crashes=3)
    assert await _until(lambda: ("queue", "failed") in states)
    assert any("not restarting" in line for _, k, line in lines if k == "status")
    count = sum(1 for n, k, line in lines if (n, line) == ("queue", "exited with code 2"))
    await asyncio.sleep(0.5)
    assert sum(1 for n, k, line in lines if (n, line) == ("queue", "exited with code 2")) == count == 3
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


async def test_restart_revives_a_given_up_worker():
    mux, task, lines, states = _start([
        Proc("server", _py("import time; time.sleep(30)"), critical=True),
        Proc("queue", _py("import sys; print('boot', flush=True); sys.exit(2)")),
    ], max_crashes=2)
    assert await _until(lambda: ("queue", "failed") in states)
    boots = sum(1 for n, k, line in lines if (n, line) == ("queue", "boot"))
    await mux.restart("queue")
    assert await _until(lambda: sum(1 for n, k, line in lines if (n, line) == ("queue", "boot")) > boots)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


async def test_manual_restart_replaces_a_running_process():
    mux, task, lines, states = _start([
        Proc("server", _py("import time; time.sleep(30)"), critical=True),
        Proc("queue", _py("import os, time; print('pid', os.getpid(), flush=True); time.sleep(30)")),
    ])
    assert await _until(lambda: any(n == "queue" and line.startswith("pid") for n, k, line in lines))
    first = next(line for n, k, line in lines if n == "queue" and line.startswith("pid"))
    await mux.restart("queue")
    assert await _until(lambda: sum(1 for n, k, line in lines if n == "queue" and line.startswith("pid")) == 2)
    pids = [line for n, k, line in lines if n == "queue" and line.startswith("pid")]
    assert pids[0] != pids[1]
    assert ("queue", "status", "restarting") in lines
    assert not any(line.startswith("exited with code") for n, k, line in lines if n == "queue")   # a deliberate restart is not a crash
    assert mux.state("server") == "running"
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


async def test_restarting_the_critical_process_does_not_end_the_run():
    mux, task, lines, _ = _start([
        Proc("server", _py("import os, time; print('pid', os.getpid(), flush=True); time.sleep(30)"), critical=True),
    ])
    assert await _until(lambda: any(line.startswith("pid") for n, k, line in lines))
    await mux.restart("server")
    assert await _until(lambda: sum(1 for n, k, line in lines if line.startswith("pid")) == 2)
    assert not task.done()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


async def test_states_are_reported():
    mux, task, lines, states = _start([
        Proc("server", _py("import time; print('UP', flush=True); time.sleep(30)"), critical=True, ready="UP"),
    ])
    assert await _until(lambda: ("server", "running") in states)
    assert states[0] == ("server", "starting")
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert ("server", "stopped") in states


async def test_no_auto_restart_leaves_the_worker_exited():
    mux, task, lines, states = _start([
        Proc("server", _py("import time; time.sleep(30)"), critical=True),
        Proc("queue", _py("import sys; sys.exit(1)")),
    ], auto_restart=False)
    assert await _until(lambda: ("queue", "exited") in states)
    await asyncio.sleep(0.4)
    assert sum(1 for n, k, line in lines if (n, line) == ("queue", "exited with code 1")) == 1
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


# ── runserver: tabbed interface when Textual is installed ────────────────────

from forgeapi.cli.commands.runserver_cmd import RunserverCommand  # noqa: E402


def _runserver(monkeypatch, args, *, textual):
    import importlib.util
    import sys
    import types

    seen = {}
    monkeypatch.setitem(sys.modules, "uvicorn", types.SimpleNamespace(run=lambda *a, **kw: seen.update(plain=True)))
    real = importlib.util.find_spec
    monkeypatch.setattr(importlib.util, "find_spec", lambda name, *a: object() if name == "textual" and textual else (None if name == "textual" else real(name, *a)))
    monkeypatch.setattr(RunserverCommand, "_run_dev", lambda self, app, host, port, reload: seen.update(dev=True, reload=reload))
    RunserverCommand().handle("runserver", args)
    return seen


def test_runserver_shows_tabs_when_textual_is_installed(monkeypatch):
    assert _runserver(monkeypatch, [], textual=True) == {"dev": True, "reload": True}


def test_runserver_is_plain_without_textual(monkeypatch):
    assert _runserver(monkeypatch, [], textual=False) == {"plain": True}


def test_no_reload_flag_in_tabs(monkeypatch):
    assert _runserver(monkeypatch, ["--no-reload"], textual=True)["reload"] is False
