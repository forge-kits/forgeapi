import secrets
from pathlib import Path


_CONFIG_PROJECT_TEMPLATE = '''\
from forgeapi import env

config = {{
    "name": "{name}",
    "version": "0.1.0",
    "description": "",
    "debug": env("APP_DEBUG", False),   # enables Telescope — never in production
    # Extra forgeapi.foundation.Provider classes to run on startup:
    "providers": [],
}}
'''

_CONFIG_HTTP_TEMPLATE = '''\
config = {
    "cors": ["*"],        # True → all origins; list → specific; False → off
    "rate_limit": 60,     # req/min per IP; False → off
    "request_id": True,   # inject X-Request-ID header
    "access_log": True,   # log method/path/status/duration per request
    "middleware": [],     # custom middleware classes or (cls, kwargs) tuples
}
'''

_CONFIG_STRUCTURE_TEMPLATE = '''\
config = {
    "models_dir": "database/models",
    "controllers_dir": "app/controllers",
    "schemas_dir": "app/schemas",
    "events_dir": "app/events",
    "listeners_dir": "app/listeners",
    "policies_dir": "app/policies",
    "seeds_dir": "database/seeds",
    "base_prefix": "/api/v1",
}
'''

_CONFIG_AUTH_TEMPLATES = {
    "jwt": '''\
from forgeapi import env

config = {
    "default": "api",
    "guards": {
        "api": {
            "strategy": "jwt",
            "secret": env("JWT_SECRET"),
            "access_ttl": 30,    # minutes
            "refresh_ttl": 7,    # days
            # "model": "database.models.user.User",  # resolve to a DB model
        },
    },
}
''',
    "cookie": '''\
from forgeapi import env

config = {
    "default": "web",
    "guards": {
        "web": {
            "strategy": "cookie",
            "secret": env("COOKIE_SECRET"),
            "cookie_name": "session",
            "httponly": True,
            "secure": False,   # set True behind HTTPS
        },
    },
}
''',
    "telegram": '''\
from forgeapi import env

config = {
    "default": "api",
    "guards": {
        "api": {
            "strategy": "telegram",
            "bot_token": env("BOT_TOKEN"),
            "max_age": 86400,   # seconds
        },
    },
}
''',
}

_CONFIG_PAGINATION_TEMPLATE = '''\
config = {
    "default_limit": 20,
    "max_limit": 100,
}
'''

# config/database.py per driver — TORTOISE_ORM lives here (Laravel-style:
# connection params in config/database); the loader derives the dotted
# path for the tortoise CLI from the file location, no "config" dict needed.
_CONFIG_DATABASE_TEMPLATES = {
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
from forgeapi import Core
from tortoise.contrib.fastapi import register_tortoise
from config.database import TORTOISE_ORM

app = FastAPI()

core = Core(app)   # everything is wired from config/

register_tortoise(
    app,
    config=TORTOISE_ORM,
    generate_schemas=False,
    add_exception_handlers=True,
)
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

    _write(root / "config/project.py", _CONFIG_PROJECT_TEMPLATE.format(name=name), name, typer)
    _write(root / "config/structure.py", _CONFIG_STRUCTURE_TEMPLATE, name, typer)
    _write(root / "config/http.py", _CONFIG_HTTP_TEMPLATE, name, typer)
    _write(root / "config/auth.py", _CONFIG_AUTH_TEMPLATES[strategy], name, typer)
    _write(root / "config/pagination.py", _CONFIG_PAGINATION_TEMPLATE, name, typer)
    _write(
        root / "config/database.py",
        _CONFIG_DATABASE_TEMPLATES[driver].format(name=name),
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
