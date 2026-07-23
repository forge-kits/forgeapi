from __future__ import annotations

from forgeapi.cli.base import Command


class RunserverCommand(Command):
    name = "runserver"
    help_text = """\
Usage: forgeapi runserver [options]

Starts the dev server via uvicorn.

Options:
  --port <N>     Port (default 8000)
  --host <addr>  Host (default 127.0.0.1)
  --reload       Auto-reload on file changes

Examples:
  forgeapi runserver
  forgeapi runserver --reload
  forgeapi runserver --port 9000 --host 0.0.0.0 --reload
"""

    def handle(self, cmd: str, args: list[str]) -> None:
        import os
        import sys
        import typer

        port = 8000
        host = "127.0.0.1"
        reload = False
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

        typer.echo(f"Starting {app_path} on {host}:{port} (reload={reload})")
        uvicorn.run(app_path, host=host, port=port, reload=reload)
