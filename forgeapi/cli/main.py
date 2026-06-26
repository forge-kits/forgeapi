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
  forgeapi generate:schema <ModelName> --payload [--crud/-cru/-cu/-d]
  forgeapi generate:schema <ModelName> --response
  forgeapi make:seed <Name>
  forgeapi db:init
  forgeapi db:makemigrations [-n <name>]
  forgeapi db:migrate
  forgeapi db:seed [<Name>...]
  forgeapi db:fresh
  forgeapi routers
  forgeapi models
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
  forgeapi generate:schema User --payload
  forgeapi generate:schema User --response
  forgeapi generate:schema User --payload --response -crud
  forgeapi runserver --port 8000 --reload

\b
Add -h after any command for detailed help:
  forgeapi make:controller -h
  forgeapi generate:schema -h
"""

_HELP_INIT = """\
Usage: forgeapi init <project-name>

Scaffolds a new ForgeAPI project. Asks for:
  auth strategy  (jwt / cookie / telegram)
  DB driver      (asyncpg / aiosqlite / aiomysql)
  welcome boilerplate (User + Post + events, optional)

Creates:
  <project-name>/
    main.py  forgeapi.toml  .env  pyproject.toml
    app/  models/  controllers/  schemas/  events/  listeners/
"""

_HELP_MAKE = """\
make: commands

  make:controller <Name>   Generate controller  (-m -s)
  make:model <Name>        Generate model       (-c -s)
  make:schema <Name>       Generate stub schemas (-m -c)
  make:event <Name>        Generate Event subclass
  make:listener <Name>     Generate @listen handler

Namespace controllers — each CamelCase word becomes a path segment:
  AdminUser      → controllers/admin/user_controller.py   /admin/users
  ApiV1User      → controllers/api/v1/user_controller.py  /api/v1/users

Flags combine: --ms  --mc  --mcs  -cs  etc.
Add -h after any subcommand for details.
"""

_HELP_MAKE_CONTROLLER = """\
Usage: forgeapi make:controller <Name> [flags]

Generates a controller in controllers_dir.
CamelCase words before the last become a namespace subdirectory.

  User              → controllers/user_controller.py
  AdminUser         → controllers/admin/user_controller.py   /admin/users
  SuperAdminUser    → controllers/super/admin/user_controller.py

Flags:
  -m, --model    Also generate Tortoise model
  -s, --schema   Also generate stub schemas
  Compound: --ms  --mc  --mcs  -ms  etc.

Examples:
  forgeapi make:controller User
  forgeapi make:controller User --ms
  forgeapi make:controller AdminUser --ms
"""

_HELP_MAKE_MODEL = """\
Usage: forgeapi make:model <Name> [flags]

Generates a Tortoise ORM model in models_dir.

Flags:
  -c, --controller   Also generate controller
  -s, --schema       Also generate stub schemas
  Compound: --cs  --mc  etc.

Examples:
  forgeapi make:model Post
  forgeapi make:model Post -cs
"""

_HELP_MAKE_SCHEMA = """\
Usage: forgeapi make:schema <Name> [flags]

Generates stub Pydantic schemas (3 classes with pass).
For typed schemas from an existing model use generate:schema.

Flags:
  -m, --model        Also generate Tortoise model
  -c, --controller   Also generate controller

Examples:
  forgeapi make:schema Post
  forgeapi make:schema Post --mc
"""

_HELP_MAKE_EVENT = """\
Usage: forgeapi make:event <Name>

Generates an Event subclass in events_dir.

Example:
  forgeapi make:event UserRegistered
  # → app/events/user_registered_event.py
"""

_HELP_MAKE_LISTENER = """\
Usage: forgeapi make:listener <Name>

Generates a @listen handler in listeners_dir.

Example:
  forgeapi make:listener UserRegistered
  # → app/listeners/user_registered_listener.py
"""

_HELP_GENERATE_SCHEMA = """\
Usage: forgeapi generate:schema <Name> --payload [crud] | --response

Reads an existing Tortoise model and generates typed Pydantic schemas.
At least one of --payload or --response is required.

  --payload   schemas/payload/<name>.py   (input / request schemas)
  --response  schemas/response/<name>.py  (always: Response + ListResponse)

CRUD flags (--payload only):
  --crud     c+r+u  (default when --payload given without CRUD flags)
  -crud      c+r+u+d  (all four, including delete)
  --cu       create + update
  --cr       create + read
  -d         delete payload only
  (any letter combo of c r u d)

Generated classes:
  payload c → {Name}CreatePayload(BaseCreateSchema)
  payload r → {Name}GetPayload(BaseModel)
  payload u → {Name}UpdatePayload(BaseUpdateSchema)
  payload d → {Name}DeletePayload(BaseModel)
  response  → {Name}Response(BaseSchema)  +  {Name}ListResponse(BaseModel)

Examples:
  forgeapi generate:schema User --payload
  forgeapi generate:schema User --response
  forgeapi generate:schema User --payload --response
  forgeapi generate:schema User --payload -crud
  forgeapi generate:schema User --payload --cu
"""

_HELP_RUNSERVER = """\
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

_HELP_DB = """\
Usage: forgeapi db:<subcommand>

Migration and seed commands.

  db:init              Init tortoise migration config
  db:makemigrations    Generate migration from model changes
  db:migrate           Apply pending migrations
  db:downgrade         Revert the last migration
  db:history           Show migration history
  db:seed              Run all seeders
  db:seed <Name>       Run specific seeder(s) by name
  db:fresh             TRUNCATE all tables (asks for confirmation)

Options for db:makemigrations:
  -n <name>   Migration name

Examples:
  forgeapi db:init
  forgeapi db:makemigrations -n add_email
  forgeapi db:migrate
  forgeapi db:seed
  forgeapi db:seed User Post
"""

_HELP_MAKE_SEED = """\
Usage: forgeapi make:seed <Name>

Generates a seeder file in seeds_dir (default: database/seeds/).

Example:
  forgeapi make:seed User
  # → database/seeds/user_seeder.py

  forgeapi make:seed AdminData
  # → database/seeds/admin_data_seeder.py
"""

_HELP_ROUTERS = """\
Usage: forgeapi routers

Scans all controllers in controllers_dir and prints every registered route.
Does not require a running database — reads route metadata at import time.

Output:
  METHOD  PATH                             HANDLER
  GET     /api/v1/users/                   UserController.index
  POST    /api/v1/users/register           UserController.register
  ...
"""

_HELP_MODELS = """\
Usage: forgeapi models

Lists all Tortoise model classes found in models_dir, their table names
and field names.
"""

_MAKE_KINDS = ("controller", "model", "schema", "event", "listener", "seed")


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
        if "-h" in args or "-H" in args:
            typer.echo(_HELP_INIT)
            raise typer.Exit()
        if len(args) < 2:
            typer.echo("Error: project name is required.  Usage: forgeapi init <project-name>", err=True)
            raise typer.Exit(code=1)
        from .commands.init_cmd import run
        run(name=args[1])
        return

    if cmd == "make":
        typer.echo(_HELP_MAKE)
        raise typer.Exit()

    if cmd.startswith("make:"):
        kind = cmd.split(":", 1)[1]
        if kind not in _MAKE_KINDS:
            typer.echo(f"Error: unknown command '{cmd}'.", err=True)
            typer.echo(f"  Available: {', '.join(f'make:{k}' for k in _MAKE_KINDS)}", err=True)
            raise typer.Exit(code=1)
        if "-h" in args or "-H" in args:
            _make_help = {
                "controller": _HELP_MAKE_CONTROLLER,
                "model":      _HELP_MAKE_MODEL,
                "schema":     _HELP_MAKE_SCHEMA,
                "event":      _HELP_MAKE_EVENT,
                "listener":   _HELP_MAKE_LISTENER,
                "seed":       _HELP_MAKE_SEED,
            }
            typer.echo(_make_help.get(kind, _HELP_MAKE))
            raise typer.Exit()
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
        if "-h" in args or "-H" in args:
            typer.echo(_HELP_GENERATE_SCHEMA)
            raise typer.Exit()
        # positional: forgeapi generate:schema <ModelName> [--payload] [--response] [--crud/-cru/-cu/...]
        # also accepts legacy: forgeapi generate:schema --model <ModelName>
        remaining = args[1:]
        model_name = next((a for a in remaining if not a.startswith("-") and a != "--model"), None)
        if not model_name:
            typer.echo(
                "Error: model name is required.\n"
                "  Example: forgeapi generate:schema User --payload",
                err=True,
            )
            raise typer.Exit(code=1)
        extra_args = [a for a in remaining if a != model_name and a != "--model"]
        from .commands.generate_schema_cmd import run as run_schema
        run_schema(model_name=model_name, extra_args=extra_args)
        return

    if cmd == "routers":
        if "-h" in args or "-H" in args:
            typer.echo(_HELP_ROUTERS)
            raise typer.Exit()
        from .commands.routers_cmd import run as run_routers
        run_routers()
        return

    if cmd == "models":
        if "-h" in args or "-H" in args:
            typer.echo(_HELP_MODELS)
            raise typer.Exit()
        from .commands.models_cmd import run as run_models
        run_models()
        return

    if cmd.startswith("db:"):
        if "-h" in args or "-H" in args:
            typer.echo(_HELP_DB)
            raise typer.Exit()
        subcmd = cmd.split(":", 1)[1]
        if subcmd == "seed":
            names = [a for a in args[1:] if not a.startswith("-")]
            from .commands.seed_cmd import run as run_seed
            run_seed(names=names)
        elif subcmd == "fresh":
            from .commands.fresh_cmd import run as run_fresh
            run_fresh()
        else:
            from .commands.db_cmd import run as run_db
            run_db(subcmd=subcmd, extra_args=args[1:])
        return

    if cmd == "runserver":
        if "-h" in args or "-H" in args:
            typer.echo(_HELP_RUNSERVER)
            raise typer.Exit()
        from .commands.runserver_cmd import run
        run(extra_args=args[1:])
        return

    typer.echo(f"Error: unknown command '{cmd}'.\n", err=True)
    typer.echo(_HELP)
    raise typer.Exit(code=1)
