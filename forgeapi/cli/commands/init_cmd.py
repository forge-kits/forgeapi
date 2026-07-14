import secrets
from pathlib import Path


_TOML_TEMPLATE = """\
[project]
name        = "{name}"
version     = "0.1.0"
description = ""

[structure]
models_dir      = "database/models"
controllers_dir = "app/controllers"
schemas_dir     = "app/schemas"
events_dir      = "app/events"
listeners_dir   = "app/listeners"
seeds_dir       = "database/seeds"
base_prefix     = "/api/v1"

[auth]
strategy = "{strategy}"
{auth_fields}
[pagination]
default_limit = 20
max_limit     = 100

[database]
tortoise_orm = "app.config.TORTOISE_ORM"
"""

_AUTH_FIELDS = {
    "jwt": """\
jwt_secret_env     = "JWT_SECRET"
access_ttl_minutes = 30
refresh_ttl_days   = 7
""",
    "cookie": """\
cookie_name     = "session"
cookie_httponly = true
cookie_secure   = false
""",
    "telegram": "",
}

_CONFIG_PY_TEMPLATES = {
    "asyncpg": """\
import os
from dotenv import load_dotenv

load_dotenv()

TORTOISE_ORM = {{
    "connections": {{
        "default": {{
            "engine": os.getenv("DB_ENGINE", "tortoise.backends.asyncpg"),
            "credentials": {{
                "host":     os.getenv("DB_HOST",     "127.0.0.1"),
                "port":     int(os.getenv("DB_PORT", "5432")),
                "user":     os.getenv("DB_USER",     "root"),
                "password": os.getenv("DB_PASSWORD", "root"),
                "database": os.getenv("DB_NAME",     "{name}"),
                "schema":   os.getenv("DB_SCHEMA",   "public"),
            }},
        }}
    }},
    "apps": {{
        "models": {{
            "models":             ["database.models", "forgeapi.permissions.models"],
            "default_connection": "default",
            "migrations":         "database.migrations",
        }}
    }},
}}
""",
    "aiosqlite": """\
import os
from dotenv import load_dotenv

load_dotenv()

TORTOISE_ORM = {{
    "connections": {{
        "default": {{
            "engine": os.getenv("DB_ENGINE", "tortoise.backends.sqlite"),
            "credentials": {{
                "file_path": os.getenv("DB_PATH", "./db.sqlite3"),
            }},
        }}
    }},
    "apps": {{
        "models": {{
            "models":             ["database.models", "forgeapi.permissions.models"],
            "default_connection": "default",
            "migrations":         "database.migrations",
        }}
    }},
}}
""",
    "aiomysql": """\
import os
from dotenv import load_dotenv

load_dotenv()

TORTOISE_ORM = {{
    "connections": {{
        "default": {{
            "engine": os.getenv("DB_ENGINE", "tortoise.backends.mysql"),
            "credentials": {{
                "host":     os.getenv("DB_HOST",     "127.0.0.1"),
                "port":     int(os.getenv("DB_PORT", "3306")),
                "user":     os.getenv("DB_USER",     "root"),
                "password": os.getenv("DB_PASSWORD", "root"),
                "database": os.getenv("DB_NAME",     "{name}"),
            }},
        }}
    }},
    "apps": {{
        "models": {{
            "models":             ["database.models", "forgeapi.permissions.models"],
            "default_connection": "default",
            "migrations":         "database.migrations",
        }}
    }},
}}
""",
}

_DB_ENV_VARS = {
    "asyncpg": """\
DB_ENGINE=tortoise.backends.asyncpg
DB_HOST=127.0.0.1
DB_PORT=5432
DB_USER=root
DB_PASSWORD=root
DB_NAME={name}
DB_SCHEMA=public
""",
    "aiosqlite": """\
DB_ENGINE=tortoise.backends.sqlite
# On Windows use forward slashes or double backslashes: DB_PATH=C:/data/db.sqlite3
DB_PATH=./db.sqlite3
""",
    "aiomysql": """\
DB_ENGINE=tortoise.backends.mysql
DB_HOST=127.0.0.1
DB_PORT=3306
DB_USER=root
DB_PASSWORD=root
DB_NAME={name}
""",
}

_ENV_VARS = {
    "jwt":      "JWT_SECRET={jwt_secret}\n\n{db_env}",
    "cookie":   "COOKIE_SECRET={cookie_secret}\n\n{db_env}",
    "telegram": "TELEGRAM_BOT_TOKEN=\n\n{db_env}",
}

_MAIN_TEMPLATE = """\
from fastapi import FastAPI
from forgeapi import Core, gate
from tortoise.contrib.fastapi import register_tortoise
from app.config import TORTOISE_ORM

app = FastAPI()

core = Core(
    app,
    auth=True,
    cors=["*"],
    rate_limit=60,
    pagination=20,
    request_id=True,
    events=True,
    permissions=True,
)

gate.discover("app/policies")

register_tortoise(
    app,
    config=TORTOISE_ORM,
    generate_schemas=False,
    add_exception_handlers=True,
)
"""

_PYPROJECT_TEMPLATE = """\
[project]
name            = "{name}"
version         = "0.1.0"
requires-python = ">=3.11"
dependencies    = [
    "forgeapi[auth,{driver}]>=0.1.0",
    "uvicorn[standard]>=0.34",
    "python-dotenv>=1.1",
]

[tool.tortoise]
tortoise_orm = "app.config.TORTOISE_ORM"
"""

_CONTROLLER_BASE = """\
from forgeapi.controllers import Controller, route

__all__ = ["Controller", "route"]
"""


def run(name: str) -> None:
    import typer

    root = Path(name)
    if root.exists():
        typer.echo(f"Error: directory '{name}' already exists.", err=True)
        raise typer.Exit(code=1)

    typer.echo("")
    typer.echo("Auth strategy:")
    typer.echo("  1. jwt       — JSON Web Tokens (stateless, Bearer header)")
    typer.echo("  2. cookie    — Cookie session (HMAC-signed, httpOnly)")
    typer.echo("  3. telegram  — Telegram Mini App (initData validation)")
    typer.echo("")

    _strategy_choices = {
        "1": "jwt", "2": "cookie", "3": "telegram",
        "jwt": "jwt", "cookie": "cookie", "telegram": "telegram",
    }
    while True:
        raw = typer.prompt("Choose [1/2/3]", default="1")
        strategy = _strategy_choices.get(raw.strip().lower())
        if strategy:
            break
        typer.echo("  Invalid choice. Enter 1, 2, or 3.", err=True)

    typer.echo("")
    typer.echo("Database driver:")
    typer.echo("  1. asyncpg   — PostgreSQL (recommended)")
    typer.echo("  2. aiosqlite — SQLite (local dev / testing)")
    typer.echo("  3. aiomysql  — MySQL / MariaDB")
    typer.echo("")

    _driver_choices = {
        "1": "asyncpg", "2": "aiosqlite", "3": "aiomysql",
        "asyncpg": "asyncpg", "aiosqlite": "aiosqlite", "aiomysql": "aiomysql",
    }
    while True:
        raw = typer.prompt("Choose [1/2/3]", default="1")
        driver = _driver_choices.get(raw.strip().lower())
        if driver:
            break
        typer.echo("  Invalid choice. Enter 1, 2, or 3.", err=True)

    typer.echo("")
    root.mkdir()

    for d in ["app/controllers", "app/schemas", "app/events", "app/listeners", "app/policies",
              "database/models", "database/migrations", "database/seeds"]:
        p = root / d
        p.mkdir(parents=True, exist_ok=True)
        (p / "__init__.py").touch()

    (root / "app" / "__init__.py").touch()

    _write(root / "app/controllers/controller.py", _CONTROLLER_BASE, name, typer)

    _write(
        root / "forgeapi.toml",
        _TOML_TEMPLATE.format(name=name, strategy=strategy, auth_fields=_AUTH_FIELDS[strategy]),
        name, typer,
    )

    _write(
        root / "app/config.py",
        _CONFIG_PY_TEMPLATES[driver].format(name=name),
        name, typer,
    )

    db_env = _DB_ENV_VARS[driver].format(name=name)
    _write(
        root / ".env",
        _ENV_VARS[strategy].format(
            jwt_secret=secrets.token_hex(32),
            cookie_secret=secrets.token_hex(32),
            db_env=db_env,
        ),
        name, typer,
    )

    _write(root / "main.py", _MAIN_TEMPLATE, name, typer)

    _write(
        root / "pyproject.toml",
        _PYPROJECT_TEMPLATE.format(name=name, driver=driver),
        name, typer,
    )

    typer.echo("")
    if typer.confirm(
        "Create a welcome project? (User + Post, events, policies, cache, permissions)", default=False
    ):
        from .boilerplate import run as run_boilerplate
        run_boilerplate(root, strategy=strategy)
    else:
        typer.echo("\nDone. Next:")
        typer.echo(f"  cd {name}")
        typer.echo("  forgeapi make:controller User --ms")
        typer.echo("  forgeapi db:init && forgeapi db:makemigrations && forgeapi db:migrate")
        typer.echo("  forgeapi runserver --reload")


def _write(path: Path, content: str, project_name: str, typer) -> None:
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    typer.echo(f"  created  {path}")
