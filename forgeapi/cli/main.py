from __future__ import annotations

import io
import os
import sys
from pathlib import Path

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from typing import List

import typer
from rich.text import Text

from forgeapi.cli import ui
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
from forgeapi.cli.commands.mcp_cmd import McpCommand
from forgeapi.cli.commands.doctor_cmd import DoctorCommand
from forgeapi.support.project import find_project_root


_COMMAND_GROUPS: list[tuple[str, list[tuple[str, str]]]] = [
    ("", [
        ("init <project-name>", "Scaffold a new project"),
        ("runserver", "Start the dev server (--port, --host, --reload)"),
        ("routers", "List all registered routes"),
        ("models", "List all discovered Tortoise models"),
        ("doctor [--no-db]", "Diagnose env, config, models and DB"),
    ]),
    ("make", [
        ("make:controller <Name>", "Create a controller (-m model, -s schemas)"),
        ("make:model <Name>", "Create a model (-c controller, -s schemas)"),
        ("make:schema <Name>", "Create stub schemas (-m model, -c controller)"),
        ("make:seed <Name>", "Create a seeder"),
        ("make:job <Name>", "Create a queue job"),
        ("make:policy <Model>", "Create a policy for a model"),
        ("make:observer <Model>", "Create a model observer"),
        ("make:provider <Name>", "Create a provider"),
        ("make:command <Name>", "Create a custom CLI command"),
    ]),
    ("generate", [
        ("generate:schema <Model>", "Generate schemas (--payload, --response)"),
    ]),
    ("db", [
        ("db:init", "Init the migration config"),
        ("db:makemigrations", "Generate a migration (-n <name>)"),
        ("db:migrate", "Apply migrations (--force: wipe, then re-run)"),
        ("db:seed [<Name>...]", "Run seeders"),
        ("db:fresh", "Truncate all tables (--force: drop them)"),
    ]),
    ("schedule", [
        ("schedule:run [<name>]", "Run due tasks once (for cron)"),
        ("schedule:work", "Run the scheduler loop (dev)"),
        ("schedule:list", "List tasks and their status"),
    ]),
    ("queue", [
        ("queue:work", "Start the queue worker (--queue=a,b)"),
        ("queue:run", "Process pending jobs once (--queue=a,b)"),
        ("queue:failed", "List failed jobs"),
        ("queue:retry <id>", "Move a failed job back to the queue"),
        ("queue:flush", "Delete all failed jobs"),
    ]),
    ("mcp", [
        ("mcp:install", "Register the MCP server (--global, --project)"),
        ("mcp:remove", "Remove the MCP server (--global, --project)"),
        ("mcp:status", "Show the MCP server status"),
    ]),
]


def _show_help() -> None:
    ui.logo()
    ui.console.print(Text.assemble("  ", ("ForgeAPI", ui.BRAND), f" {ui.package_version()}  ", ("FastAPI toolkit", "dim")))
    ui.blank()
    ui.console.print(Text(" Usage:", style="bold yellow"))
    ui.console.print("  forgeapi <command> [options]")
    ui.blank()
    ui.console.print(Text(" Available commands:", style="bold yellow"))
    found, errors = _load_project_commands(quiet=True)
    rows = [(c.name, c.description) for c in {id(c): c for c in found.values()}.values()]
    ui.render_commands(_COMMAND_GROUPS + ([("project", rows)] if rows else []))
    for error in errors:
        ui.warn(f"project commands: {error}")
    ui.blank()
    ui.console.print(Text.assemble("  Add ", ("-h", "green"), " after any command for details, e.g. ", ("forgeapi make:controller -h", "dim")))
    ui.blank()


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
_mcp_cmd = McpCommand()

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
    _mcp_cmd,
    DoctorCommand(),
])
_registry.register_prefix("make:", _make_cmd)
_registry.register_prefix("db:", _db_cmd)
_registry.register_prefix("schedule:", _schedule_cmd)
_registry.register_prefix("queue:", _queue_cmd)
_registry.register_prefix("mcp:", _mcp_cmd)


def _load_project_commands(*, quiet: bool) -> tuple[dict[str, Command], list[str]]:
    """Commands from the project's ``commands_dir`` as ``{name or alias: command}``, plus problems.

    Built-in names always win: a project command that reuses one is skipped and reported.
    Returns nothing outside a project. ``quiet`` skips the "Using project root" notice (help listing).
    """
    root = find_project_root(Path.cwd())
    if root is None:
        return {}, []
    if quiet:
        os.chdir(root)
    else:
        _enter_project()

    from forgeapi.cli import project_commands

    try:
        from forgeapi.config import load_config

        commands, errors = project_commands.discover(load_config().structure.commands_dir)
    except Exception as exc:
        return {}, [f"{type(exc).__name__}: {exc}"]

    found: dict[str, Command] = {}
    for cmd in commands:
        names = (cmd.name, *cmd.aliases)
        taken = next((n for n in names if _registry.find(n) is not None or n in found), None)
        if taken is not None:
            errors.append(f"{cmd.name}: the name '{taken}' is already taken, skipped")
            continue
        for n in names:
            found[n] = cmd
    return found, errors


def _resolve(cmd_name: str, *, quiet: bool) -> tuple[Command | None, list[str]]:
    """A built-in command, else a project command; the list holds project-command problems."""
    cmd = _registry.find(cmd_name)
    if cmd is not None:
        return cmd, []
    found, errors = _load_project_commands(quiet=quiet)
    return found.get(cmd_name), errors


app = typer.Typer(
    name="forgeapi",
    add_completion=False,
    pretty_exceptions_enable=False,
    no_args_is_help=False,
)


def _enter_project() -> None:
    """Run from the project root, or stop: file-writing commands must never guess a location."""
    here = Path.cwd().resolve()
    root = find_project_root(here)
    if root is None:
        ui.error(
            f"No ForgeAPI project found in [{here}] or its parent directories.",
            hint="cd into your project (the folder with config/), or create one: forgeapi init <project-name>",
        )
        raise typer.Exit(code=1)
    if root != here:
        os.chdir(root)
        ui.console.print(Text(f"  Using project root: {root}", style="dim"), soft_wrap=True)


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
        _show_help()
        raise typer.Exit()

    cmd_name = args[0]
    rest = args[1:]

    if any(a in rest for a in ("-h", "-H", "--help", "--h")):
        cmd, _ = _resolve(cmd_name, quiet=True)
        if cmd:
            cmd.show_help(cmd_name)
        else:
            _show_help()
        raise typer.Exit()

    cmd, problems = _resolve(cmd_name, quiet=False)
    if cmd is None:
        for problem in problems:
            ui.warn(f"project commands: {problem}")
        ui.error(f"Command '{cmd_name}' is not defined.", hint="Run `forgeapi` to see the available commands.")
        raise typer.Exit(code=1)

    if cmd.needs_project(cmd_name):
        _enter_project()
    cmd.handle(cmd_name, rest)
