from __future__ import annotations

import asyncio
import importlib
import sys
from pathlib import Path

import typer

from forgeapi.cli import ui
from forgeapi.cli.base import Command
from forgeapi.config import load_config

# Applied-migrations bookkeeping (tortoise.migrations.recorder.MigrationRecorder). Dropping it
# along with the data tables is what makes a later db:migrate start from the first migration;
# truncating must leave it alone or the applied state would be lost.
_HISTORY_TABLES = {"tortoise_migrations", "aerich"}

_LIST_TABLES_SQL = {
    "sqlite": (
        "SELECT '' AS schema_name, name AS table_name FROM sqlite_master "
        "WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
    ),
    "mysql": (
        "SELECT '' AS schema_name, table_name AS table_name FROM information_schema.tables "
        "WHERE table_schema = DATABASE() AND table_type = 'BASE TABLE'"
    ),
    "postgres": (
        "SELECT schemaname AS schema_name, tablename AS table_name FROM pg_tables "
        "WHERE schemaname = current_schema()"
    ),
}

_DROP_SQL = {
    "postgres": "DROP TABLE IF EXISTS {ref} CASCADE",
    "mysql": "DROP TABLE IF EXISTS {ref}",
    "sqlite": "DROP TABLE IF EXISTS {ref}",
}
_TRUNCATE_SQL = {
    "postgres": "TRUNCATE TABLE {ref} RESTART IDENTITY CASCADE",
    "mysql": "TRUNCATE TABLE {ref}",
    "sqlite": "DELETE FROM {ref}",
}


class FreshCommand(Command):
    name = "db:fresh"

    def handle(self, cmd: str, args: list[str]) -> None:
        force = "--force" in args
        if force:
            self.drop_everything(assume_yes=_wants_yes(args))
            ui.info("Run `forgeapi db:migrate` to recreate the tables.")
            return

        user_config = self.load_orm_config()
        if not _wants_yes(args):
            typer.confirm("This will TRUNCATE every table in the database (data only). Continue?", abort=True)
        done, failed = asyncio.run(self._apply(user_config, _TRUNCATE_SQL, include_history=False))
        self._report("Truncated", done, failed)

    def load_orm_config(self) -> dict:
        cfg = load_config()
        orm_path = cfg.database.tortoise_orm

        cwd = str(Path.cwd())
        if cwd not in sys.path:
            sys.path.insert(0, cwd)

        module_path, var_name = orm_path.rsplit(".", 1)
        try:
            mod = importlib.import_module(module_path)
            return getattr(mod, var_name)
        except (ImportError, AttributeError) as exc:
            self.abort(f"cannot import {orm_path}: {exc}")

    def drop_everything(self, *, assume_yes: bool = False) -> None:
        """Drop every model table and the migration history. Asks first unless *assume_yes*."""
        user_config = self.load_orm_config()
        ui.warn("This will DROP every table in the database (structure + data) and the migration history.")
        if not assume_yes:
            typer.confirm("Continue?", abort=True)
        done, failed = asyncio.run(self._apply(user_config, _DROP_SQL, include_history=True))
        self._report("Dropped", done, failed)
        if failed:
            self.abort("not every table could be dropped — fix the errors above and re-run.")

    @staticmethod
    def _report(verb: str, done: list[str], failed: list[tuple[str, str]]) -> None:
        ui.blank()
        for label in done:
            ui.leader(label, "DONE")
        for label, reason in failed:
            ui.leader(label, "FAIL", kind="error")
            ui.console.print(f"    {reason}", style="dim")
        ui.blank()
        if failed:
            ui.warn(f"{verb} {len(done)} table(s), {len(failed)} failed.")
        else:
            ui.success(f"{verb} {len(done)} table(s).")

    @staticmethod
    def _detect_engine(config: dict) -> str:
        conn = config.get("connections", {}).get("default", {})
        if isinstance(conn, str):
            url = conn.lower()
            if url.startswith("sqlite"):
                return "sqlite"
            if url.startswith("mysql"):
                return "mysql"
            return "postgres"
        engine = conn.get("engine", "")
        if "sqlite" in engine:
            return "sqlite"
        if "mysql" in engine:
            return "mysql"
        return "postgres"

    @staticmethod
    def _quote(name: str, engine: str) -> str:
        return f"`{name}`" if engine == "mysql" else f'"{name}"'

    async def _list_tables(self, conn, engine: str) -> list[tuple[str, str]]:
        """Every base table the connection can see, as ``(schema, table)``.

        Asks the database rather than the models: many-to-many through tables and tables that
        belong to no model would otherwise survive and break the next ``db:migrate``.
        """
        _, rows = await conn.execute_query(_LIST_TABLES_SQL[engine])
        return [(row["schema_name"], row["table_name"]) for row in rows]

    async def _apply(
        self,
        config: dict,
        templates: dict[str, str],
        *,
        include_history: bool,
    ) -> tuple[list[str], list[tuple[str, str]]]:
        """Run ``templates[engine]`` for every table in the database.

        The migration history table is skipped unless *include_history*. Returns
        ``(done, failed)`` — *failed* holds ``(table, reason)`` so a statement that did not go
        through is reported instead of silently leaving the table behind.
        """
        from tortoise import Tortoise

        await Tortoise.init(config=config)
        conn = Tortoise.get_connection("default")
        engine = self._detect_engine(config)
        template = templates[engine]

        targets = []
        for schema, table in await self._list_tables(conn, engine):
            if table in _HISTORY_TABLES and not include_history:
                continue
            ref = self._quote(table, engine)
            if schema:
                ref = f"{self._quote(schema, engine)}.{ref}"
            targets.append((f"{schema}.{table}" if schema else table, ref))

        # Children and parents are removed in arbitrary order: let the engine skip FK checks.
        guard_off, guard_on = {
            "mysql": ("SET FOREIGN_KEY_CHECKS = 0", "SET FOREIGN_KEY_CHECKS = 1"),
            "sqlite": ("PRAGMA foreign_keys = OFF", "PRAGMA foreign_keys = ON"),
        }.get(engine, (None, None))

        done: list[str] = []
        failed: list[tuple[str, str]] = []
        try:
            if guard_off:
                await conn.execute_query(guard_off)
            for label, ref in targets:
                try:
                    await conn.execute_query(template.format(ref=ref))
                    done.append(label)
                except Exception as exc:
                    failed.append((label, str(exc)))
            if guard_on:
                await conn.execute_query(guard_on)
        finally:
            await Tortoise.close_connections()
        return done, failed


def _wants_yes(args: list[str]) -> bool:
    return "--yes" in args or "-y" in args
