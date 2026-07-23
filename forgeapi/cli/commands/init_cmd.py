from __future__ import annotations

import secrets
from pathlib import Path

from forgeapi.cli.base import Command


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
    "listeners_dir": "app/listeners",
    "policies_dir": "app/policies",
    "seeds_dir": "database/seeds",
    "base_prefix": "/api/v1",
}
'''

_CONFIG_BROADCAST_TEMPLATE = '''\
from forgeapi import BroadcastManager

config = {{}}  # required by config loader — broadcast is configured below

broadcast = BroadcastManager(
    driver="redis",
    url="redis://localhost:6379",
    namespace="{name}",
    mode="stream",   # "pubsub" = fire-and-forget | "stream" = persistent
    maxlen=1000,
)
'''

_CONFIG_STORAGE_TEMPLATE = '''\
from forgeapi import env

config = {
    "driver": "local",        # "local" | "s3"
    "root": "storage/app",    # local: filesystem root
    "base_url": "/storage",   # local: public URL prefix
    # S3 / MinIO / Cloudflare R2:
    # "bucket": "my-bucket",
    # "region": "us-east-1",
    # "access_key": env("AWS_ACCESS_KEY_ID"),
    # "secret_key": env("AWS_SECRET_ACCESS_KEY"),
    # "endpoint_url": "",     # MinIO / R2 endpoint
}
'''

_CONFIG_AUTH_TEMPLATES = {
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
            "models": [
                "database.models", 
                "forgeapi.scheduling.models", 
                "forgeapi.queue.models", 
                "forgeapi.permissions.models"
            ],
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
            "models":             ["database.models", "forgeapi.scheduling.models", "forgeapi.queue.models", "forgeapi.permissions.models"],
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
            "models":             ["database.models", "forgeapi.scheduling.models", "forgeapi.queue.models", "forgeapi.permissions.models"],
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
    "cookie":   "COOKIE_SECRET={cookie_secret}\n\n{db_env}",
    "telegram": "TELEGRAM_BOT_TOKEN=\n\n{db_env}",
}

_MAIN_TEMPLATE = """\
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from forgeapi import Core
from tortoise.contrib.fastapi import register_tortoise
from config.database import TORTOISE_ORM

# Optional: enable broadcasting (Redis required — configure in config/broadcast.py)
# from config.broadcast import broadcast

# Optional: run scheduler in-process (or use CLI: forgeapi schedule:work)
# from schedule import scheduler

@asynccontextmanager
async def lifespan(app):
    # await broadcast.connect(group="{name}", consumer="worker-1")
    # task = asyncio.create_task(scheduler.run())
    yield
    # await broadcast.disconnect()
    # task.cancel()

app = FastAPI(lifespan=lifespan)

core = Core(app)   # everything is wired from config/

register_tortoise(
    app,
    config=TORTOISE_ORM,
    generate_schemas=False,
    add_exception_handlers=True,
)
"""

_SCHEDULE_TEMPLATE = """\
from forgeapi import Scheduler

scheduler = Scheduler()

# scheduler.call(my_task).daily_at("09:00").name("my-task")
# scheduler.call(cleanup).every(30).name("cleanup")
#
# Run via CLI:
#   forgeapi schedule:work          # dev loop
#   forgeapi schedule:run           # run due tasks once (cron)
#   forgeapi schedule:run my-task   # run specific task manually
#   forgeapi schedule:list          # show all tasks and status
"""

_CONTROLLER_BASE = """\
from forgeapi.controllers import Controller, route

__all__ = ["Controller", "route"]
"""


class InitCommand(Command):
    name = "init"
    help_text = """\
Usage: forgeapi init <project-name>

Scaffolds a new ForgeAPI project. Asks for:
  auth strategy  (cookie / telegram)
  DB driver      (asyncpg / aiosqlite / aiomysql)

Creates:
  <project-name>/
    main.py  .env
    config/  app/  database/
"""

    def handle(self, cmd: str, args: list[str]) -> None:
        if not args:
            self.abort("project name is required.  Usage: forgeapi init <project-name>")

        import typer
        name = args[0]
        root = Path(name)

        if root.exists():
            self.abort(f"directory '{name}' already exists.")

        strategy = self._prompt_strategy(typer)
        driver = self._prompt_driver(typer)

        typer.echo("")
        root.mkdir()

        for d in ["app/controllers", "app/schemas", "app/listeners", "app/policies",
                  "database/models", "database/migrations", "database/seeds"]:
            p = root / d
            p.mkdir(parents=True, exist_ok=True)
            (p / "__init__.py").touch()

        (root / "app" / "__init__.py").touch()

        self._write(root / "app/controllers/controller.py", _CONTROLLER_BASE, typer)
        self._write(root / "config/project.py", _CONFIG_PROJECT_TEMPLATE.format(name=name), typer)
        self._write(root / "config/structure.py", _CONFIG_STRUCTURE_TEMPLATE, typer)
        self._write(root / "config/http.py", _CONFIG_HTTP_TEMPLATE, typer)
        self._write(root / "config/auth.py", _CONFIG_AUTH_TEMPLATES[strategy], typer)
        self._write(root / "config/pagination.py", _CONFIG_PAGINATION_TEMPLATE, typer)
        self._write(root / "config/storage.py", _CONFIG_STORAGE_TEMPLATE, typer)
        self._write(root / "config/broadcast.py", _CONFIG_BROADCAST_TEMPLATE.format(name=name), typer)
        self._write(
            root / "config/database.py",
            _CONFIG_DATABASE_TEMPLATES[driver].format(name=name),
            typer,
        )
        db_env = _DB_ENV_VARS[driver].format(name=name)
        self._write(
            root / ".env",
            _ENV_VARS[strategy].format(
                cookie_secret=secrets.token_hex(32),
                db_env=db_env,
            ),
            typer,
        )
        self._write(root / "main.py", _MAIN_TEMPLATE.format(name=name), typer)
        self._write(root / "schedule.py", _SCHEDULE_TEMPLATE, typer)

        typer.echo("\nDone. Next:")
        typer.echo(f"  cd {name}")
        typer.echo("  forgeapi make:controller User --ms")
        typer.echo("  forgeapi db:init && forgeapi db:makemigrations && forgeapi db:migrate")
        typer.echo("  forgeapi runserver --reload")

    def _prompt_strategy(self, typer) -> str:
        typer.echo("")
        typer.echo("Auth strategy:")
        typer.echo("  1. cookie    — Cookie session (HMAC-signed, httpOnly)")
        typer.echo("  2. telegram  — Telegram Mini App (initData validation)")
        typer.echo("")
        choices = {
            "1": "cookie", "2": "telegram",
            "cookie": "cookie", "telegram": "telegram",
        }
        while True:
            raw = typer.prompt("Choose [1/2]", default="1")
            strategy = choices.get(raw.strip().lower())
            if strategy:
                return strategy
            typer.echo("  Invalid choice. Enter 1 or 2.", err=True)

    def _prompt_driver(self, typer) -> str:
        typer.echo("")
        typer.echo("Database driver:")
        typer.echo("  1. asyncpg   — PostgreSQL (recommended)")
        typer.echo("  2. aiosqlite — SQLite (local dev / testing)")
        typer.echo("  3. aiomysql  — MySQL / MariaDB")
        typer.echo("")
        choices = {
            "1": "asyncpg", "2": "aiosqlite", "3": "aiomysql",
            "asyncpg": "asyncpg", "aiosqlite": "aiosqlite", "aiomysql": "aiomysql",
        }
        while True:
            raw = typer.prompt("Choose [1/2/3]", default="1")
            driver = choices.get(raw.strip().lower())
            if driver:
                return driver
            typer.echo("  Invalid choice. Enter 1, 2, or 3.", err=True)

    @staticmethod
    def _write(path: Path, content: str, typer) -> None:
        if path.exists():
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        typer.echo(f"  created  {path}")
