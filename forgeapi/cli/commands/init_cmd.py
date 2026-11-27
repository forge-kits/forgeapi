from __future__ import annotations

import os
import subprocess
from pathlib import Path

from rich.text import Text

from forgeapi.cli import ui
from forgeapi.cli.base import Command


_AUTH_BLOCKS = {
    "cookie": '''\
    "auth": {
        "default": "web",
        "guards": {
            "web": {
                "strategy": "cookie",
                "model": "database.models.user.User",
                "session_model": "database.models.session.Session",
                "cookie_name": "session",
                "lifetime": 3600,   # seconds of inactivity until the session expires
                "httponly": True,
                "secure": False,    # set True behind HTTPS
            },
        },
    },
''',
    "telegram": '''\
    "auth": {
        "default": "api",
        "guards": {
            "api": {
                "strategy": "telegram",
                "model": "database.models.user.User",
                "bot_token": env("BOT_TOKEN"),
                "max_age": 86400,   # seconds
            },
        },
    },
''',
}

# config/app.py: every setting except the database. A feature is on while its key is there.
_CONFIG_APP_TEMPLATE = '''\
from forgeapi import env

config = {
    # project
    "name": "{name}",
    "version": "0.1.0",
    "description": "",
    "api_prefix": "/api/v1",                 # URL prefix of every controller route
    "debug": env("APP_DEBUG", False),        # verbose forgeapi logging, never in production
    "timezone": env("APP_TIMEZONE", "UTC"),  # IANA name (e.g. "Europe/Sofia"), used by the scheduler and the queue
    "providers": [],                         # extra forgeapi.foundation.Provider classes to run on startup

    # A feature is on while its key is here. Comment the key out to switch it off.
{auth}
    "http": {
        "cors": ["*"],         # True = all origins, list = specific, False = off
        "cors_allow_credentials": False,   # needs explicit origins in "cors", not "*"
        "rate_limit": 60,      # req/min per IP, False = off
        "request_id": False,   # inject X-Request-ID header
        "access_log": False,   # log method/path/status/duration per request
        "middleware": [],      # custom middleware classes or (cls, kwargs) tuples
    },

    "pagination": {
        "default_limit": 20,
        "max_limit": 100,
    },

    "storage": {
        "driver": "local",        # "local" | "s3"
        "root": "storage/app",    # local: filesystem root
        "base_url": "/storage",   # local: public URL prefix
        # S3 / MinIO / Cloudflare R2:
        # "bucket": "my-bucket",
        # "region": "us-east-1",
        # "access_key": env("AWS_ACCESS_KEY_ID"),
        # "secret_key": env("AWS_SECRET_ACCESS_KEY"),
        # "endpoint_url": "",     # MinIO / R2 endpoint
    },

    "cache": {
        "driver": "database",   # "database" (table from forgeapi.cache.models) | "redis" (pip install forge-kits[redis])
        "prefix": "",           # prepended to every key, useful when projects share one Redis
        "ttl": None,            # default lifetime in seconds, None = forever
        # "redis_url": env("REDIS_URL", "redis://localhost:6379/0"),
    },

    "mail": {
        "driver": "log",                          # "log" (dev: writes to the log) | "smtp"
        "from_address": "noreply@{name}.local",
        "from_name": "{name}",
        "templates": "app/templates/mail",        # Jinja2 templates for Mailable classes
        # SMTP needs: pip install forge-kits[mail]
        # "smtp": {
        #     "host": env("MAIL_HOST", "localhost"),
        #     "port": 587,
        #     "username": env("MAIL_USERNAME", ""),
        #     "password": env("MAIL_PASSWORD", ""),
        #     "encryption": "starttls",           # "starttls" | "ssl" | None
        # },
    },

    "broadcast": {
        "driver": "redis",
        "driver_options": {
            "url": env("REDIS_URL", "redis://localhost:6379"),
            "namespace": "{name}",
            "mode": "pubsub",       # "pubsub" = fire-and-forget | "stream" = persistent
            # "maxlen": 1000,       # stream mode: keep last N messages per key
            # "group": "backend",   # stream mode: consumer group name
            # "consumer": "worker-1",
        },
    },

    # Opt-in features. Uncomment the models in config/database.py, run `forgeapi db:makemigrations`,
    # then uncomment the key.
    # "queue": {"queue": "default"},               # needs forgeapi.queue.models
    # "scheduler": {"schedule": "schedule.py"},    # needs forgeapi.scheduling.models and a schedule.py
}
'''


def _config_app(name: str, strategy: str) -> str:
    return _CONFIG_APP_TEMPLATE.replace("{auth}", _AUTH_BLOCKS[strategy]).replace("{name}", name)

_USER_MODEL_TEMPLATES = {
    "cookie": '''\
from tortoise import fields
from tortoise.models import Model

from forgeapi.database import ModelMixin


class User(ModelMixin, Model):
    id = fields.IntField(primary_key=True)
    name = fields.CharField(max_length=255)
    email = fields.CharField(max_length=255, unique=True)
    password = fields.CharField(max_length=255)   # store a hash, never the plain password
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "users"
''',
    "telegram": '''\
from tortoise import fields
from tortoise.models import Model

from forgeapi.database import ModelMixin


class User(ModelMixin, Model):
    # The telegram guard looks the user up by primary key, so the key is the Telegram user id.
    id = fields.BigIntField(primary_key=True, generated=False)
    username = fields.CharField(max_length=64, null=True)
    first_name = fields.CharField(max_length=255, null=True)
    last_name = fields.CharField(max_length=255, null=True)
    photo_url = fields.CharField(max_length=512, null=True)
    language_code = fields.CharField(max_length=16, null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    @property
    def full_name(self) -> str:
        return " ".join(p for p in (self.first_name, self.last_name) if p)

    class Meta:
        table = "users"
''',
}

_MODELS_INIT = {
    "cookie": '''\
from .password_reset_token import PasswordResetToken
from .session import Session
from .user import User

__all__ = ["PasswordResetToken", "Session", "User"]
''',
    "telegram": '''\
from .user import User

__all__ = ["User"]
''',
}

# cookie strategy: the session and password reset tables belong to the project, so they can be changed
_SESSION_MODEL_TEMPLATE = '''\
from tortoise import fields
from tortoise.models import Model


class Session(Model):
    # the cookie holds a random token, this table holds only its SHA-256 hash
    id = fields.CharField(max_length=64, primary_key=True)
    user_id = fields.CharField(max_length=255, db_index=True)
    guard = fields.CharField(max_length=64)    # a session of one guard never logs in to another
    ip_address = fields.CharField(max_length=45, null=True)
    user_agent = fields.CharField(max_length=255, null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    last_activity = fields.DatetimeField()
    expires_at = fields.DatetimeField(db_index=True)

    class Meta:
        table = "sessions"
'''

_PASSWORD_RESET_TOKEN_MODEL_TEMPLATE = '''\
from tortoise import fields
from tortoise.models import Model


class PasswordResetToken(Model):
    email = fields.CharField(max_length=255, primary_key=True)
    token = fields.CharField(max_length=255)   # store a hash, never the plain token
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "password_reset_tokens"
'''

# config/database.py per driver — TORTOISE_ORM lives here
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
    "use_tz": True,
    "timezone": os.getenv("APP_TIMEZONE", "UTC"),   # same .env value as config/app.py
    "apps": {{
        "models": {{
            "models": [
                "database.models",
                # opt-in tables of the built-in features: uncomment, then run `forgeapi db:makemigrations`
                # "forgeapi.queue.models",         # queue jobs
                # "forgeapi.scheduling.models",    # scheduler
                # "forgeapi.cache.models",         # cache driver "database"
                # "forgeapi.permissions.models",   # roles and permissions
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
    "use_tz": True,
    "timezone": os.getenv("APP_TIMEZONE", "UTC"),   # same .env value as config/app.py
    "apps": {{
        "models": {{
            "models": [
                "database.models",
                # opt-in tables of the built-in features: uncomment, then run `forgeapi db:makemigrations`
                # "forgeapi.queue.models",         # queue jobs
                # "forgeapi.scheduling.models",    # scheduler
                # "forgeapi.cache.models",         # cache driver "database"
                # "forgeapi.permissions.models",   # roles and permissions
            ],
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
    "use_tz": True,
    "timezone": os.getenv("APP_TIMEZONE", "UTC"),   # same .env value as config/app.py
    "apps": {{
        "models": {{
            "models": [
                "database.models",
                # opt-in tables of the built-in features: uncomment, then run `forgeapi db:makemigrations`
                # "forgeapi.queue.models",         # queue jobs
                # "forgeapi.scheduling.models",    # scheduler
                # "forgeapi.cache.models",         # cache driver "database"
                # "forgeapi.permissions.models",   # roles and permissions
            ],
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
    "cookie":   "APP_TIMEZONE=UTC\n\n{db_env}",
    "telegram": "APP_TIMEZONE=UTC\nTELEGRAM_BOT_TOKEN=\n\n{db_env}",
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


class InitCommand(Command):
    name = "init"
    requires_project = False
    help_text = """\
Usage: forgeapi init <project-name>

Scaffolds a new ForgeAPI project. Asks for:
  auth strategy  (cookie / telegram)
  DB driver      (asyncpg / aiosqlite / aiomysql)

Creates:
  <project-name>/
    main.py  .env
    config/  app/  database/   (incl. database/models/user.py, the auth user model,
                               and session.py + password_reset_token.py for the cookie strategy)
"""

    def handle(self, cmd: str, args: list[str]) -> None:
        if not args:
            self.abort("project name is required.  Usage: forgeapi init <project-name>")

        import typer
        name = args[0]
        root = Path(name)

        if root.exists():
            self.abort(f"directory '{name}' already exists.")

        ui.blank()
        ui.console.print(Text.assemble("  ", ("ForgeAPI", ui.BRAND), f" {ui.package_version()}  ", ("new project", "dim")))
        ui.blank()

        strategy = ui.choose("Auth strategy", [
            ("cookie", "cookie", "Cookie session (kept in the database, httpOnly)"),
            ("telegram", "telegram", "Telegram Mini App (initData validation)"),
        ])
        ui.blank()
        driver = ui.choose("Database driver", [
            ("asyncpg", "asyncpg", "PostgreSQL (recommended)"),
            ("aiosqlite", "aiosqlite", "SQLite (local dev / testing)"),
            ("aiomysql", "aiomysql", "MySQL / MariaDB"),
        ])

        ui.blank()
        ui.info(f"Creating project [{name}].")
        ui.summary([("Auth", strategy), ("Database", driver)])
        ui.blank()
        root.mkdir()

        # policies, commands, mail, listeners, ... are not scaffolded: their make:* command creates the folder
        for d in ["app/controllers", "app/schemas",
                  "database/models", "database/migrations", "database/seeds", "database/factories"]:
            p = root / d
            p.mkdir(parents=True, exist_ok=True)
            (p / "__init__.py").touch()

        (root / "app" / "__init__.py").touch()

        (root / "database/models/__init__.py").write_text(_MODELS_INIT[strategy], encoding="utf-8")
        ui.file_event("created", str(root / "database/models/__init__.py"))
        self._write(root / "database/models/user.py", _USER_MODEL_TEMPLATES[strategy], typer)
        if strategy == "cookie":
            self._write(root / "database/models/session.py", _SESSION_MODEL_TEMPLATE, typer)
            self._write(
                root / "database/models/password_reset_token.py", _PASSWORD_RESET_TOKEN_MODEL_TEMPLATE, typer
            )
        self._write(root / "app/controllers/controller.py", _CONTROLLER_BASE, typer)
        self._write(root / "config/app.py", _config_app(name, strategy), typer)
        self._write(
            root / "config/database.py",
            _CONFIG_DATABASE_TEMPLATES[driver].format(name=name),
            typer,
        )
        db_env = _DB_ENV_VARS[driver].format(name=name)
        self._write(
            root / ".env",
            _ENV_VARS[strategy].format(
                db_env=db_env,
            ),
            typer,
        )
        self._write(root / "main.py", _MAIN_TEMPLATE.format(name=name), typer)

        migrated = self._make_initial_migration(root)

        ui.blank()
        ui.success(f"Project [{name}] created.")
        ui.blank()
        ui.next_steps("Next steps", [
            f"cd {name}",
            "forgeapi db:migrate" if migrated
            else "forgeapi db:init && forgeapi db:makemigrations && forgeapi db:migrate",
            "forgeapi make:controller Post --ms",
            "forgeapi runserver --reload",
        ])
        ui.blank()

    @staticmethod
    def _make_initial_migration(root: Path) -> bool:
        """Run ``db:init`` + ``db:makemigrations`` inside the new project.

        The first migration creates the tables of the generated models (the users table,
        plus the session and password reset tables for the cookie strategy).
        Returns ``True`` when ``database/migrations/0001_create_users_table.py`` was generated.
        On any failure prints a warning and returns ``False`` so the caller can
        fall back to the manual commands - scaffolding itself never fails here.
        """
        from .db_cmd import DbCommand

        tortoise_bin = DbCommand._find_tortoise_bin()
        if tortoise_bin is None:
            ui.warn("tortoise binary not found - skipped the initial migration.")
            return False

        env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
        orm = "config.database.TORTOISE_ORM"   # the default path, same as KitConfig.database.tortoise_orm
        for sub in (["init"], ["makemigrations", "--name", "create_users_table"]):
            try:
                result = subprocess.run(
                    [tortoise_bin, "-c", orm, *sub],
                    cwd=root, env=env, capture_output=True, text=True, timeout=120,
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                ui.warn(f"initial migration skipped: {exc}")
                return False
            if result.returncode != 0:
                ui.warn(f"initial migration skipped: 'tortoise {sub[0]}' failed.")
                ui.indented((result.stderr or result.stdout).strip()[-600:])
                return False

        created = sorted((root / "database" / "migrations").glob("0001_*.py"))
        if not created:
            ui.warn("initial migration skipped: no migration file was generated.")
            return False
        ui.file_event("created", str(created[0]))
        return True

    @staticmethod
    def _write(path: Path, content: str, typer) -> None:
        if path.exists():
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        ui.file_event("created", str(path))
