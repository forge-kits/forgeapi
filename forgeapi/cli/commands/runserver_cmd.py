from __future__ import annotations

import sys
from pathlib import Path

from forgeapi.cli.base import Command
from forgeapi.cli.multiplex import Proc


def _forgeapi_argv(*args: str) -> list[str]:
    """Run another forgeapi command with the interpreter that runs this one."""
    return [sys.executable, "-c", "from forgeapi.cli.main import app; app()", *args]


def plan_processes(cfg, *, app_path: str, host: str, port: int, reload: bool) -> list[Proc]:
    """The processes of ``runserver --dev``: the server first, then every worker the config enables."""
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


def choose_mode(requested: str | None, *, interactive: bool, has_textual: bool) -> tuple[str, str]:
    """``(mode, hint)`` for ``runserver --dev``: ``"tabs"``, ``"stream"`` or ``"inline"``.

    Without a request the tabbed interface is used when there is a terminal and Textual is installed,
    otherwise plain output.  ``hint`` explains a fallback ("" when there is nothing to say).
    """
    if requested == "inline":
        return "inline", ""
    if not interactive:
        return "inline", ""
    if not has_textual:
        return "inline", "tabs and search need Textual: pip install forge-kits[dev]. Showing plain output."
    return requested or "tabs", ""


class RunserverCommand(Command):
    name = "runserver"
    help_text = """\
Usage: forgeapi runserver [options]

Starts the dev server via uvicorn.

Options:
  --port <N>     Port (default 8000)
  --host <addr>  Host (default 127.0.0.1)
  --reload       Auto-reload on file changes
  --dev          Run the server, the queue worker and the scheduler as separate
                 processes in one terminal. Reload is on (--no-reload turns it off).
                 Needs a terminal. With `pip install forge-kits[dev]` it shows one tab
                 per process (plus `logs`); without it, plain prefixed output.

Options for --dev:
  -t, --tabs     Tabs, one per process (default)
  -s, --stream   One interleaved stream (switch with `m` while running)
  -i, --inline   Plain prefixed output, no interface (also used without a terminal)
  --timestamps   Show the time of every line
  --no-restart   Do not restart a worker that crashed

Keys in the interface: Tab/Shift+Tab or 1-9 switch tabs, r restart the process of the
current tab, / search, m tabs/stream, t timestamps, c clear, q quit.

Examples:
  forgeapi runserver
  forgeapi runserver --reload
  forgeapi runserver --dev
  forgeapi runserver --dev --stream --timestamps
  forgeapi runserver --port 9000 --host 0.0.0.0 --reload
"""

    def handle(self, cmd: str, args: list[str]) -> None:
        import os
        from forgeapi.cli import ui

        port = 8000
        host = "127.0.0.1"
        reload: bool | None = None
        dev = False
        mode: str | None = None
        timestamps = False
        auto_restart = True
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
            elif arg == "--dev":
                dev = True
                i += 1
            elif arg in ("--tabs", "-t"):
                mode = "tabs"
                i += 1
            elif arg in ("--stream", "-s"):
                mode = "stream"
                i += 1
            elif arg in ("--inline", "-i"):
                mode = "inline"
                i += 1
            elif arg == "--timestamps":
                timestamps = True
                i += 1
            elif arg == "--no-restart":
                auto_restart = False
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

        if dev:
            self._run_dev(app_path, host, port, True if reload is None else reload,
                          mode=mode, timestamps=timestamps, auto_restart=auto_restart)
            return

        reload = bool(reload)
        ui.server_started(app_path, host, port, reload)
        uvicorn.run(app_path, host=host, port=port, reload=reload)

    def _run_dev(
        self,
        app_path: str,
        host: str,
        port: int,
        reload: bool,
        *,
        mode: str | None = None,
        timestamps: bool = False,
        auto_restart: bool = True,
    ) -> None:
        import asyncio
        import importlib.util

        import typer

        from forgeapi.cli import ui
        from forgeapi.cli.multiplex import Multiplexer
        from forgeapi.config import load_config

        procs = plan_processes(load_config(), app_path=app_path, host=host, port=port, reload=reload)
        names = [p.name for p in procs]
        mode, hint = choose_mode(
            mode,
            interactive=sys.stdin.isatty() and sys.stdout.isatty(),
            has_textual=importlib.util.find_spec("textual") is not None,
        )
        if hint:
            ui.warn(hint)

        if mode != "inline":
            from forgeapi.cli.devui import DevApp

            muxes: list[Multiplexer] = []

            def factory(emit, on_state):
                mux = Multiplexer(procs, emit, on_state=on_state, auto_restart=auto_restart)
                muxes.append(mux)
                return mux

            app = DevApp(factory, names, stream=mode == "stream", timestamps=timestamps)
            try:
                code = app.run() or 0
            finally:
                for mux in muxes:
                    mux.kill_now()
            if code:
                raise typer.Exit(code=code)
            return

        ui.dev_started(app_path, host, port, reload, [
            (p.name, f"http://{host}:{port}" if p.critical else "forgeapi " + p.argv[-1]) for p in procs
        ])
        mux = Multiplexer(procs, ui.process_printer(names, timestamps=timestamps), auto_restart=auto_restart)
        code = 0
        try:
            code = asyncio.run(mux.run())
        except KeyboardInterrupt:
            pass
        finally:
            mux.kill_now()
        if code:
            raise typer.Exit(code=code)
