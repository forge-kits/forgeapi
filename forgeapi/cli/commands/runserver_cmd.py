from typing import List


def run(extra_args: List[str]) -> None:
    import typer

    port = 8000
    host = "127.0.0.1"
    reload = False
    app_path = "main:app"

    i = 0
    while i < len(extra_args):
        arg = extra_args[i]
        if arg in ("--port", "-p") and i + 1 < len(extra_args):
            port = int(extra_args[i + 1])
            i += 2
        elif arg in ("--host", "-h") and i + 1 < len(extra_args):
            host = extra_args[i + 1]
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
        typer.echo("Error: uvicorn is not installed. Run: pip install uvicorn", err=True)
        raise typer.Exit(code=1)

    import sys
    import os
    cwd = os.getcwd()
    if cwd not in sys.path:
        sys.path.insert(0, cwd)

    typer.echo(f"Starting {app_path} on {host}:{port} (reload={reload})")
    uvicorn.run(app_path, host=host, port=port, reload=reload)
