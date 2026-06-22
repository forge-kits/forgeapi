import io
import sys

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from typing import List
import typer

app = typer.Typer(
    name="forgeapi",
    add_completion=False,
    pretty_exceptions_enable=False,
    no_args_is_help=False,
)

_HELP = """\
ForgeAPI — Boilerplate for FastAPI.

\b
Commands:
  forgeapi init <project-name>
  forgeapi make:controller <Name>   [-m] [-s]
  forgeapi make:model <Name>        [-c] [-s]
  forgeapi make:schema <Name>       [-m] [-c]
  forgeapi make:event <Name>
  forgeapi make:listener <Name>
  forgeapi generate:schema <ModelName>
  forgeapi db:init
  forgeapi db:makemigrations [-n <name>]
  forgeapi db:migrate
  forgeapi db:downgrade
  forgeapi db:history
  forgeapi runserver [--port 8000] [--host 127.0.0.1] [--reload]

\b
Flags for make:controller / make:model / make:schema:
  -m, --model         Also generate model
  -c, --controller    Also generate controller
  -s, --schema        Also generate schema
  Compound: --ms  --mc  --cs  --mcs  (any order of letters)

\b
Examples:
  forgeapi init my-blog
  forgeapi make:controller User --ms
  forgeapi make:model Post -cs
  forgeapi make:schema Order --mc
  forgeapi make:event UserRegistered
  forgeapi make:listener UserRegistered
  forgeapi generate:schema User
  forgeapi runserver --port 8000 --reload
"""

_MAKE_KINDS = ("controller", "model", "schema", "event", "listener")


@app.command(
    name=None,
    context_settings={
        "allow_extra_args": True,
        "ignore_unknown_options": True,
        "help_option_names": [],  # we handle -h / --help ourselves
    },
)
def main(ctx: typer.Context) -> None:
    args: List[str] = ctx.args

    if not args or args[0] in ("--help", "-h", "--h", "help"):
        typer.echo(_HELP)
        raise typer.Exit()

    cmd = args[0]

    if cmd == "init":
        if len(args) < 2:
            typer.echo("Error: project name is required.  Usage: forgeapi init <project-name>", err=True)
            raise typer.Exit(code=1)
        from .commands.init_cmd import run
        run(name=args[1])
        return

    if cmd.startswith("make:"):
        kind = cmd.split(":", 1)[1]
        if kind not in _MAKE_KINDS:
            typer.echo(f"Error: unknown command '{cmd}'.", err=True)
            typer.echo(f"  Available: {', '.join(f'make:{k}' for k in _MAKE_KINDS)}", err=True)
            raise typer.Exit(code=1)
        if len(args) < 2 or args[1].startswith("-"):
            typer.echo(f"Error: name is required.  Example: forgeapi make:{kind} MyName", err=True)
            raise typer.Exit(code=1)
        name = args[1]
        from .commands.generate_cmd import parse_flags, run_make
        flags, unknown = parse_flags(args[2:])
        if unknown:
            typer.echo(f"Error: unknown flags: {' '.join(unknown)}", err=True)
            raise typer.Exit(code=1)
        run_make(kind=kind, name=name, flags=flags)
        return

    if cmd == "generate:schema":
        # positional: forgeapi generate:schema <ModelName>
        # also accepts legacy: forgeapi generate:schema --model <ModelName>
        remaining = [a for a in args[1:] if a != "--model"]
        model_name = remaining[0] if remaining else None
        if not model_name or model_name.startswith("-"):
            typer.echo("Error: model name is required.  Example: forgeapi generate:schema User", err=True)
            raise typer.Exit(code=1)
        from .commands.generate_schema_cmd import run as run_schema
        run_schema(model_name=model_name)
        return

    if cmd.startswith("db:"):
        subcmd = cmd.split(":", 1)[1]
        from .commands.db_cmd import run as run_db
        run_db(subcmd=subcmd, extra_args=args[1:])
        return

    if cmd == "runserver":
        from .commands.runserver_cmd import run
        run(extra_args=args[1:])
        return

    typer.echo(f"Error: unknown command '{cmd}'.\n", err=True)
    typer.echo(_HELP)
    raise typer.Exit(code=1)
