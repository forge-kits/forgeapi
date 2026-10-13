from __future__ import annotations

import asyncio
import copy
import importlib
import importlib.util
import sys
from pathlib import Path

from forgeapi.cli.base import Command

OK, WARN, FAIL = "ok", "warn", "fail"

_DRIVERS = {
    "asyncpg": "asyncpg",
    "sqlite": "aiosqlite",
    "mysql": "aiomysql",
}

# config section -> models module that feature needs registered in Tortoise
_FEATURE_MODELS = {
    "scheduler": "forgeapi.scheduling.models",
    "queue": "forgeapi.queue.models",
    "permissions": "forgeapi.permissions.models",
}


class DoctorCommand(Command):
    name = "doctor"
    help_text = """\
Usage: forgeapi doctor [--no-db]

Checks the project setup and reports problems:

  environment   Python version, .env file, required packages, DB driver
  config        config/ loads and validates, project directories exist
  tortoise      TORTOISE_ORM imports, model modules import, feature models registered
  scheduler     schedule.py defines a valid `scheduler`
  database      connection works, every registered model has its table (run db:migrate)

Options:
  --no-db   Skip the database connection and table checks

Exit code is 1 when any check fails (warnings do not fail).
"""

    def __init__(self) -> None:
        self.results: list[tuple[str, str, str]] = []

    # ── result helpers ──────────────────────────────────────────────────────────

    def _add(self, level: str, title: str, hint: str = "") -> None:
        self.results.append((level, title, hint))

    def handle(self, cmd: str, args: list[str]) -> None:
        import typer

        self.results = []
        cwd = str(Path.cwd())
        if cwd not in sys.path:
            sys.path.insert(0, cwd)

        self._check_environment()
        cfg = self._check_config()
        tortoise_config = None
        if cfg is not None:
            self._check_structure(cfg)
            tortoise_config = self._check_tortoise(cfg)
            self._check_scheduler(cfg)
            if tortoise_config is not None and "--no-db" not in args:
                asyncio.run(self._check_database(tortoise_config))

        icons = {OK: "ok  ", WARN: "warn", FAIL: "FAIL"}
        typer.echo("")
        for level, title, hint in self.results:
            typer.echo(f"  [{icons[level]}] {title}")
            if hint and level != OK:
                typer.echo(f"         -> {hint}")
        fails = sum(1 for r in self.results if r[0] == FAIL)
        warns = sum(1 for r in self.results if r[0] == WARN)
        typer.echo(f"\n  {len(self.results) - fails - warns} ok, {warns} warning(s), {fails} failed\n")
        if fails:
            raise typer.Exit(code=1)

    # ── checks ──────────────────────────────────────────────────────────────────

    def _check_environment(self) -> None:
        v = sys.version_info
        if v < (3, 11):
            self._add(FAIL, f"Python {v.major}.{v.minor}", "forgeapi needs Python 3.11+ (see requires-python)")
        else:
            self._add(OK, f"Python {v.major}.{v.minor}.{v.micro}")

        if Path(".env").exists():
            self._add(OK, ".env found")
        else:
            self._add(WARN, ".env not found", "copy .env.example or create .env if config uses env()")

        for pkg in ("fastapi", "tortoise", "pydantic"):
            if importlib.util.find_spec(pkg) is None:
                self._add(FAIL, f"package '{pkg}' is not installed", f"pip install {pkg}")

    def _check_config(self):
        from forgeapi.config import load_config

        if not Path("config").is_dir():
            self._add(WARN, "config/ directory not found", "using defaults; run `forgeapi init` for a template")
        try:
            cfg = load_config()
        except Exception as exc:
            self._add(FAIL, "config failed to load", str(exc))
            return None
        provided = sorted(s for s in ("auth", "database", "cache", "storage", "broadcast", "scheduler", "queue")
                          if cfg.provided(s))
        self._add(OK, "config loaded" + (f" (sections: {', '.join(provided)})" if provided else ""))
        return cfg

    def _check_structure(self, cfg) -> None:
        st = cfg.structure
        for label, path in (
            ("models_dir", st.models_dir),
            ("controllers_dir", st.controllers_dir),
            ("schemas_dir", st.schemas_dir),
        ):
            if Path(path).is_dir():
                self._add(OK, f"{label}: {path}")
            else:
                self._add(WARN, f"{label} '{path}' does not exist", "fix config/project.py structure or create it")

    def _load_tortoise_dict(self, cfg) -> dict | None:
        try:
            module_dotted, attr = cfg.database.tortoise_orm.rsplit(".", 1)
            mod = importlib.import_module(module_dotted)
            return getattr(mod, attr)
        except Exception as exc:
            self._add(FAIL, f"cannot import {cfg.database.tortoise_orm}", str(exc))
            return None

    def _check_tortoise(self, cfg) -> dict | None:
        tc = self._load_tortoise_dict(cfg)
        if tc is None:
            return None
        if not isinstance(tc, dict) or not tc.get("connections") or not tc.get("apps"):
            self._add(FAIL, "TORTOISE_ORM must define 'connections' and 'apps'")
            return None
        self._add(OK, f"TORTOISE_ORM loaded from {cfg.database.tortoise_orm}")

        project_tz = cfg.project.timezone
        if project_tz and tc.get("timezone", "UTC") != project_tz:
            self._add(
                WARN,
                f"project timezone '{project_tz}' differs from TORTOISE_ORM timezone '{tc.get('timezone', 'UTC')}'",
                'set "timezone": os.getenv("APP_TIMEZONE", "UTC") in config/database.py, same as config/project.py',
            )

        all_modules: list[str] = []
        for app_name, app_cfg in tc["apps"].items():
            for module in app_cfg.get("models", []):
                all_modules.append(module)
                try:
                    importlib.import_module(module)
                except Exception as exc:
                    self._add(FAIL, f"app '{app_name}': model module '{module}' fails to import", str(exc))

        for section, module in _FEATURE_MODELS.items():
            if section == "permissions":
                continue  # no config section; only a hint when the module is missing but used
            if cfg.provided(section) and module not in all_modules:
                self._add(
                    WARN,
                    f"config/{section}.py exists but '{module}' is not in TORTOISE_ORM models",
                    "add it to config/database.py, otherwise db:makemigrations will not create its tables "
                    "(schedule:/queue: commands create them at runtime instead)",
                )

        for conn_name, conn in tc["connections"].items():
            engine = conn if isinstance(conn, str) else conn.get("engine", "")
            engine = engine.lower()
            driver = next((pkg for key, pkg in _DRIVERS.items() if key in engine), None)
            if driver is None:
                continue
            if importlib.util.find_spec(driver) is None:
                self._add(FAIL, f"connection '{conn_name}' needs the '{driver}' package", f"pip install {driver}")
            else:
                self._add(OK, f"DB driver '{driver}' installed")
        return tc

    def _check_scheduler(self, cfg) -> None:
        if not cfg.provided("scheduler") and not Path(cfg.structure.schedule_file).exists():
            return
        path = Path(cfg.scheduler.schedule if cfg.provided("scheduler") else cfg.structure.schedule_file)
        if not path.exists():
            self._add(WARN, f"schedule file '{path}' not found", "create it with a `scheduler = Scheduler()` variable")
            return
        try:
            spec = importlib.util.spec_from_file_location("_doctor_schedule", path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
        except Exception as exc:
            self._add(FAIL, f"'{path}' fails to import", str(exc))
            return
        from forgeapi.scheduling import Scheduler

        scheduler = getattr(mod, "scheduler", None)
        if not isinstance(scheduler, Scheduler):
            self._add(FAIL, f"'{path}' must define `scheduler = Scheduler()`")
            return
        bad = [j._label for j in scheduler._jobs if j._schedule_type is None]
        names = [j._label for j in scheduler._jobs]
        dupes = sorted({n for n in names if names.count(n) > 1})
        if bad:
            self._add(FAIL, f"jobs without a schedule: {', '.join(bad)}", "call .daily_at(), .cron(), etc.")
        if dupes:
            self._add(FAIL, f"duplicate job names: {', '.join(dupes)}", "names must be unique (use .name())")
        if not bad and not dupes:
            self._add(OK, f"schedule: {len(names)} job(s) valid")

    @staticmethod
    def _engine(config: dict) -> str:
        conn = config.get("connections", {}).get("default", "")
        engine = conn if isinstance(conn, str) else conn.get("engine", "")
        return engine.lower()

    async def _check_database(self, tortoise_config: dict) -> None:
        from tortoise import Tortoise

        config = copy.deepcopy(tortoise_config)
        try:
            await Tortoise.init(config=config)
            conn = Tortoise.get_connection("default")
            await conn.execute_query("SELECT 1")
        except Exception as exc:
            self._add(FAIL, "database connection failed", str(exc))
            try:
                await Tortoise.close_connections()
            except Exception:
                pass
            return
        self._add(OK, "database connection works")

        engine = self._engine(config)
        q = "`" if "mysql" in engine else '"'
        missing: list[str] = []
        for app_models in Tortoise.apps.values():
            for model in app_models.values():
                schema = getattr(model._meta, "schema", None)
                table = model._meta.db_table
                ref = f"{q}{schema}{q}.{q}{table}{q}" if schema else f"{q}{table}{q}"
                try:
                    await conn.execute_query(f"SELECT 1 FROM {ref} WHERE 1=0")
                except Exception:
                    missing.append(f"{schema}.{table}" if schema else table)
        if missing:
            self._add(FAIL, f"tables missing: {', '.join(sorted(missing))}", "run forgeapi db:makemigrations && forgeapi db:migrate")
        else:
            self._add(OK, "all model tables exist")
        await Tortoise.close_connections()
