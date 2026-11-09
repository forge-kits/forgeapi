from __future__ import annotations

import os
import secrets
import subprocess
from pathlib import Path

from rich.text import Text

from forgeapi.cli import ui
from forgeapi.cli.base import Command


_CONFIG_PROJECT_TEMPLATE = '''\
from forgeapi import env

config = {{
    "name": "{name}",
    "version": "0.1.0",
    "description": "",
    "debug": env("APP_DEBUG", False),   # verbose forgeapi logging — never in production
    "timezone": env("APP_TIMEZONE", "UTC"),  # IANA name (e.g. "Europe/Sofia") — scheduler, queue
    # Extra forgeapi.foundation.Provider classes to run on startup:
    "providers": [],
}}
'''

_CONFIG_HTTP_TEMPLATE = '''\
config = {
    "cors": ["*"],        # True → all origins; list → specific; False → off
    "allow_credentials": False,
    "rate_limit": 60,     # req/min per IP; False → off
    "request_id": False,   # inject X-Request-ID header
    "access_log": False,   # log method/path/status/duration per request
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
    "jobs_dir": "app/jobs",
    "observers_dir": "app/observers",
    "providers_dir": "app/providers",
    "commands_dir": "app/commands",
    "seeds_dir": "database/seeds",
    "base_prefix": "/api/v1",
}
'''

_CONFIG_BROADCAST_TEMPLATE = '''\
from forgeapi import env

config = {{
    "enabled": True,
    "driver": "redis",
    "driver_options": {{
        "url": env("REDIS_URL", "redis://localhost:6379"),
        "namespace": "{name}",
        "mode": "pubsub",       # "pubsub" = fire-and-forget | "stream" = persistent
        # "maxlen": 1000,       # stream mode: keep last N messages per key
        # "group": "backend",   # stream mode: consumer group name
        # "consumer": "worker-1",
    }},
}}
'''

_CONFIG_SCHEDULER_TEMPLATE = '''\
config = {
    "enabled": True,
    "schedule": "schedule.py",   # path to your schedule.py relative to project root
}
'''

_CONFIG_QUEUE_TEMPLATE = '''\
config = {
    "enabled": True,
    "queue": "default",   # queue name the in-process worker will consume
}
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
            "model": "database.models.user.User",
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
            "model": "database.models.user.User",
            "bot_token": env("BOT_TOKEN"),
            "max_age": 86400,   # seconds
        },
    },
}
''',
}

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

_USER_MODELS_INIT = '''\
from .user import User

__all__ = ["User"]
'''

_CONFIG_PAGINATION_TEMPLATE = '''\
config = {
    "default_limit": 20,
    "max_limit": 100,
}
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
    "timezone": os.getenv("APP_TIMEZONE", "UTC"),   # same .env value as config/project.py
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
    "use_tz": True,
    "timezone": os.getenv("APP_TIMEZONE", "UTC"),   # same .env value as config/project.py
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
    "use_tz": True,
    "timezone": os.getenv("APP_TIMEZONE", "UTC"),   # same .env value as config/project.py
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
    "cookie":   "APP_TIMEZONE=UTC\nCOOKIE_SECRET={cookie_secret}\n\n{db_env}",
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
    requires_project = False
    help_text = """\
Usage: forgeapi init <project-name>

Scaffolds a new ForgeAPI project. Asks for:
  auth strategy  (cookie / telegram)
  DB driver      (asyncpg / aiosqlite / aiomysql)

Creates:
  <project-name>/
    main.py  .env
    config/  app/  database/   (incl. database/models/user.py, the auth user model)
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
            ("cookie", "cookie", "Cookie session (HMAC-signed, httpOnly)"),
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

        for d in ["app/controllers", "app/schemas", "app/listeners", "app/policies", "app/commands",
                  "database/models", "database/migrations", "database/seeds"]:
            p = root / d
            p.mkdir(parents=True, exist_ok=True)
            (p / "__init__.py").touch()

        (root / "app" / "__init__.py").touch()

        (root / "database/models/__init__.py").write_text(_USER_MODELS_INIT, encoding="utf-8")
        ui.file_event("created", str(root / "database/models/__init__.py"))
        self._write(root / "database/models/user.py", _USER_MODEL_TEMPLATES[strategy], typer)
        self._write(root / "app/controllers/controller.py", _CONTROLLER_BASE, typer)
        self._write(root / "config/project.py", _CONFIG_PROJECT_TEMPLATE.format(name=name), typer)
        self._write(root / "config/structure.py", _CONFIG_STRUCTURE_TEMPLATE, typer)
        self._write(root / "config/http.py", _CONFIG_HTTP_TEMPLATE, typer)
        self._write(root / "config/auth.py", _CONFIG_AUTH_TEMPLATES[strategy], typer)
        self._write(root / "config/pagination.py", _CONFIG_PAGINATION_TEMPLATE, typer)
        self._write(root / "config/storage.py", _CONFIG_STORAGE_TEMPLATE, typer)
        self._write(root / "config/broadcast.py", _CONFIG_BROADCAST_TEMPLATE.format(name=name), typer)
        self._write(root / "config/scheduler.py", _CONFIG_SCHEDULER_TEMPLATE, typer)
        self._write(root / "config/queue.py", _CONFIG_QUEUE_TEMPLATE, typer)
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

        Returns ``True`` when ``database/migrations/0001_*.py`` was generated.
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
        for sub in ("init", "makemigrations"):
            try:
                result = subprocess.run(
                    [tortoise_bin, "-c", orm, sub],
                    cwd=root, env=env, capture_output=True, text=True, timeout=120,
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                ui.warn(f"initial migration skipped: {exc}")
                return False
            if result.returncode != 0:
                ui.warn(f"initial migration skipped: 'tortoise {sub}' failed.")
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
