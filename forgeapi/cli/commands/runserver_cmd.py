from __future__ import annotations

import sys
from pathlib import Path

from forgeapi.cli.base import Command
from forgeapi.cli.multiplex import Proc


def _forgeapi_argv(*args: str) -> list[str]:
    """Run another forgeapi command with the interpreter that runs this one."""
    return [sys.executable, "-c", "from forgeapi.cli.main import app; app()", *args]


def plan_processes(cfg, *, app_path: str, host: str, port: int, reload: bool) -> list[Proc]:
    """The processes of the dev ``runserver``: the server first, then every worker the config enables."""
    from forgeapi.support.workers import EXTERNAL_WORKERS_ENV

    workers: list[Proc] = []
    if cfg.provided("queue") and cfg.queue.enabled:
        workers.append(Proc("queue", _forgeapi_argv("queue:work"), ready="Queue worker started"))
    if cfg.provided("scheduler") and cfg.scheduler.enabled and Path(cfg.scheduler.schedule).exists():
        workers.append(Proc("schedule", _forgeapi_argv("schedule:work"), ready="Scheduler running"))

    web_argv = [sys.executable, "-m", "uvicorn", app_path, "--host", host, "--port", str(port), "--use-colors"]
    if reload:
        web_argv.append("--reload")
    # the workers run on their own now: the web process must not start its embedded copies
    web_env = {EXTERNAL_WORKERS_ENV: "1"} if workers else {}
    return [Proc("server", web_argv, critical=True, env=web_env, ready="Application startup complete"), *workers]


class RunserverCommand(Command):
    name = "runserver"
    help_text = """\
Usage: forgeapi runserver [options]

Starts the dev server via uvicorn. With `pip install forge-kits[dev]` it runs the server,
the queue worker and the scheduler as separate processes in one terminal, one tab per
process (plus `logs`), with reload on. Without it, only the web server starts.

Options:
  --port <N>     Port (default 8000)
  --host <addr>  Host (default 127.0.0.1)
  --reload       Auto-reload on file changes (always on in the tabbed interface)
  --no-reload    Turn reload off in the tabbed interface

Keys in the tabbed interface: Tab/Shift+Tab or 1-9 switch tabs, r restart the process of
the current tab, / search, m tabs/stream, t timestamps, c clear, q quit.

Examples:
  forgeapi runserver
  forgeapi runserver --reload
  forgeapi runserver --port 9000 --host 0.0.0.0 --reload
"""

    def handle(self, cmd: str, args: list[str]) -> None:
        import os
        from forgeapi.cli import ui

        port = 8000
        host = "127.0.0.1"
        reload: bool | None = None
        app_path = "main:app"

        i = 0
        while i < len(args):
            arg = args[i]
            if arg in ("--port", "-p") and i + 1 < len(args):
                port = int(args[i + 1])
                i += 2
            elif arg in ("--host", "-h") and i + 1 < len(args):
                host = args[i + 1]
                i += 2
            elif arg == "--reload":
                reload = True
                i += 1
            elif arg == "--no-reload":
                reload = False
                i += 1
            elif not arg.startswith("-"):
                app_path = arg
                i += 1
            else:
                i += 1

        try:
            import uvicorn
        except ImportError:
            self.abort("uvicorn is not installed. Run: pip install uvicorn")

        cwd = os.getcwd()
        if cwd not in sys.path:
            sys.path.insert(0, cwd)

        import importlib.util

        if importlib.util.find_spec("textual") is not None:
            self._run_dev(app_path, host, port, True if reload is None else reload)
            return

        reload = bool(reload)
        ui.server_started(app_path, host, port, reload)
        uvicorn.run(app_path, host=host, port=port, reload=reload)

    def _run_dev(self, app_path: str, host: str, port: int, reload: bool) -> None:
        import typer

        from forgeapi.cli.devui import DevApp
        from forgeapi.cli.multiplex import Multiplexer
        from forgeapi.config import load_config

        procs = plan_processes(load_config(), app_path=app_path, host=host, port=port, reload=reload)
        muxes: list[Multiplexer] = []

        def factory(emit, on_state):
            mux = Multiplexer(procs, emit, on_state=on_state)
            muxes.append(mux)
            return mux

        app = DevApp(factory, [p.name for p in procs])
        try:
            code = app.run() or 0
        finally:
            for mux in muxes:
                mux.kill_now()
        if code:
            raise typer.Exit(code=code)
