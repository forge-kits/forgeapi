from __future__ import annotations

import io
import sys

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from typing import List
import typer

from forgeapi.cli.base import Command
from forgeapi.cli.commands.init_cmd import InitCommand
from forgeapi.cli.commands.generate_cmd import MakeCommand
from forgeapi.cli.commands.generate_schema_cmd import GenerateSchemaCommand
from forgeapi.cli.commands.db_cmd import DbCommand
from forgeapi.cli.commands.seed_cmd import SeedCommand
from forgeapi.cli.commands.fresh_cmd import FreshCommand
from forgeapi.cli.commands.routers_cmd import RoutersCommand
from forgeapi.cli.commands.schedule_cmd import ScheduleCommand
from forgeapi.cli.commands.queue_cmd import QueueCommand
from forgeapi.cli.commands.models_cmd import ModelsCommand
from forgeapi.cli.commands.runserver_cmd import RunserverCommand


_HELP = """\
ForgeAPI — Boilerplate for FastAPI.

\b
Commands:
  forgeapi init <project-name>
  forgeapi make:controller <Name>   [-m] [-s]
  forgeapi make:model <Name>        [-c] [-s]
  forgeapi make:schema <Name>       [-m] [-c]
  forgeapi generate:schema <ModelName> --payload [--crud/-cru/-cu/-d]
  forgeapi generate:schema <ModelName> --response
  forgeapi make:seed <Name>
  forgeapi db:init
  forgeapi db:makemigrations [-n <name>]
  forgeapi db:migrate
  forgeapi db:seed [<Name>...]
  forgeapi db:fresh
  forgeapi schedule:run [<name>]
  forgeapi schedule:work
  forgeapi schedule:list
  forgeapi queue:work
  forgeapi queue:run
  forgeapi queue:failed
  forgeapi queue:retry <id>
  forgeapi queue:flush
  forgeapi routers
  forgeapi models
  forgeapi runserver [--port 8000] [--host 127.0.0.1] [--reload]

\b
Add -h after any command for detailed help:
  forgeapi make:controller -h
  forgeapi generate:schema -h
"""


class CommandRegistry:
    def __init__(self, commands: list[Command]) -> None:
        self._exact: dict[str, Command] = {}
        self._prefixes: list[tuple[str, Command]] = []

        for cmd in commands:
            self._exact[cmd.name] = cmd
            for alias in cmd.aliases:
                self._exact[alias] = cmd

    def register_prefix(self, prefix: str, cmd: Command) -> None:
        self._prefixes.append((prefix, cmd))

    def find(self, name: str) -> Command | None:
        if name in self._exact:
            return self._exact[name]
        for prefix, cmd in self._prefixes:
            if name.startswith(prefix):
                return cmd
        return None


_make_cmd = MakeCommand()
_db_cmd = DbCommand()
_schedule_cmd = ScheduleCommand()
_queue_cmd = QueueCommand()

_registry = CommandRegistry([
    InitCommand(),
    _make_cmd,
    GenerateSchemaCommand(),
    RoutersCommand(),
    ModelsCommand(),
    RunserverCommand(),
    SeedCommand(),
    FreshCommand(),
    _db_cmd,
    _schedule_cmd,
    _queue_cmd,
])
_registry.register_prefix("make:", _make_cmd)
_registry.register_prefix("db:", _db_cmd)
_registry.register_prefix("schedule:", _schedule_cmd)
_registry.register_prefix("queue:", _queue_cmd)


app = typer.Typer(
    name="forgeapi",
    add_completion=False,
    pretty_exceptions_enable=False,
    no_args_is_help=False,
)


@app.command(
    name=None,
    context_settings={
        "allow_extra_args": True,
        "ignore_unknown_options": True,
        "help_option_names": [],
    },
)
def main(ctx: typer.Context) -> None:
    args: List[str] = ctx.args

    if not args or args[0] in ("--help", "-h", "--h", "help"):
        typer.echo(_HELP)
        raise typer.Exit()

    cmd_name = args[0]
    rest = args[1:]

    if "-h" in rest or "-H" in rest:
        cmd = _registry.find(cmd_name)
        if cmd:
            cmd.show_help(cmd_name)
        else:
            typer.echo(_HELP)
        raise typer.Exit()

    cmd = _registry.find(cmd_name)
    if cmd is None:
        typer.echo(f"Error: unknown command '{cmd_name}'.\n", err=True)
        typer.echo(_HELP)
        raise typer.Exit(code=1)

    cmd.handle(cmd_name, rest)
