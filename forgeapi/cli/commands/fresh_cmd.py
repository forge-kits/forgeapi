from __future__ import annotations

import asyncio
import importlib
import sys
from pathlib import Path

import typer

from forgeapi.cli.base import Command
from forgeapi.config import load_config

_SKIP_TABLES = {"aerich"}


class FreshCommand(Command):
    name = "db:fresh"

    def handle(self, cmd: str, args: list[str]) -> None:
        force = "--force" in args
        cfg = load_config()
        orm_path = cfg.database.tortoise_orm

        cwd = str(Path.cwd())
        if cwd not in sys.path:
            sys.path.insert(0, cwd)

        module_path, var_name = orm_path.rsplit(".", 1)
        try:
            mod = importlib.import_module(module_path)
            user_config: dict = getattr(mod, var_name)
        except (ImportError, AttributeError) as exc:
            self.abort(f"cannot import {orm_path}: {exc}")

        if force:
            typer.echo(
                "WARNING: --force will DROP all tables (structure + data).\n"
                "You will need to run migrations again before the app can start.",
            )
            typer.confirm("This will DROP all tables. Continue?", abort=True)
            tables = asyncio.run(self._drop_all(user_config))
            for table in tables:
                typer.echo(f"  dropped: {table}")
            typer.echo(f"\nDone — {len(tables)} table(s) dropped.")
        else:
            typer.confirm("This will TRUNCATE all tables (data only). Continue?", abort=True)
            tables = asyncio.run(self._truncate_all(user_config))
            for table in tables:
                typer.echo(f"  truncated: {table}")
            typer.echo(f"\nDone — {len(tables)} table(s) cleared.")

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
    def _sql_ref(model, engine: str = "postgres") -> str:
        schema = getattr(model._meta, "schema", None)
        table = model._meta.db_table
        if engine == "mysql":
            return f"`{table}`"
        return f'"{schema}"."{table}"' if schema else f'"{table}"'

    @staticmethod
    def _label(model) -> str:
        schema = getattr(model._meta, "schema", None)
        table = model._meta.db_table
        return f"{schema}.{table}" if schema else table

    async def _drop_all(self, config: dict) -> list[str]:
        from tortoise import Tortoise

        await Tortoise.init(config=config)
        conn = Tortoise.get_connection("default")
        engine = self._detect_engine(config)

        model_list = [
            model
            for app_models in Tortoise.apps.values()
            for model in app_models.values()
            if model._meta.db_table not in _SKIP_TABLES
        ]

        dropped = []
        if engine == "mysql":
            await conn.execute_query("SET FOREIGN_KEY_CHECKS = 0")
            for model in model_list:
                try:
                    await conn.execute_query(f"DROP TABLE IF EXISTS {self._sql_ref(model, engine)}")
                    dropped.append(self._label(model))
                except Exception:
                    pass
            await conn.execute_query("SET FOREIGN_KEY_CHECKS = 1")
        elif engine == "sqlite":
            for model in model_list:
                try:
                    await conn.execute_query(f"DROP TABLE IF EXISTS {self._sql_ref(model, engine)}")
                    dropped.append(self._label(model))
                except Exception:
                    pass
        else:
            for model in model_list:
                try:
                    await conn.execute_query(
                        f"DROP TABLE IF EXISTS {self._sql_ref(model, engine)} CASCADE"
                    )
                    dropped.append(self._label(model))
                except Exception:
                    pass

        await Tortoise.close_connections()
        return dropped

    async def _truncate_all(self, config: dict) -> list[str]:
        from tortoise import Tortoise

        await Tortoise.init(config=config)
        conn = Tortoise.get_connection("default")
        engine = self._detect_engine(config)

        model_list = [
            model
            for app_models in Tortoise.apps.values()
            for model in app_models.values()
            if model._meta.db_table not in _SKIP_TABLES
        ]

        truncated = []
        if engine == "mysql":
            await conn.execute_query("SET FOREIGN_KEY_CHECKS = 0")
            for model in model_list:
                try:
                    await conn.execute_query(f"TRUNCATE TABLE {self._sql_ref(model, engine)}")
                    truncated.append(self._label(model))
                except Exception:
                    pass
            await conn.execute_query("SET FOREIGN_KEY_CHECKS = 1")
        elif engine == "sqlite":
            for model in model_list:
                try:
                    await conn.execute_query(f"DELETE FROM {self._sql_ref(model, engine)}")
                    truncated.append(self._label(model))
                except Exception:
                    pass
        else:
            for model in model_list:
                try:
                    await conn.execute_query(
                        f"TRUNCATE TABLE {self._sql_ref(model, engine)} RESTART IDENTITY CASCADE"
                    )
                    truncated.append(self._label(model))
                except Exception:
                    pass

        await Tortoise.close_connections()
        return truncated
