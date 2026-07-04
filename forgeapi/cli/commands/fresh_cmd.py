import asyncio
import importlib
import sys
from pathlib import Path

import typer

from forgeapi.config import load_config

_SKIP_TABLES = {"aerich"}


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


async def _drop_all(config: dict) -> list[str]:
    from tortoise import Tortoise

    await Tortoise.init(config=config)
    conn = Tortoise.get_connection("default")
    engine = _detect_engine(config)

    def _sql_ref(model, eng: str = "postgres") -> str:
        schema = getattr(model._meta, "schema", None)
        table = model._meta.db_table
        if eng == "mysql":
            return f"`{table}`"
        return f'"{schema}"."{table}"' if schema else f'"{table}"'

    def _label(model) -> str:
        schema = getattr(model._meta, "schema", None)
        table = model._meta.db_table
        return f"{schema}.{table}" if schema else table

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
                await conn.execute_query(f"DROP TABLE IF EXISTS {_sql_ref(model, engine)}")
                dropped.append(_label(model))
            except Exception:
                pass
        await conn.execute_query("SET FOREIGN_KEY_CHECKS = 1")
    elif engine == "sqlite":
        for model in model_list:
            try:
                await conn.execute_query(f"DROP TABLE IF EXISTS {_sql_ref(model, engine)}")
                dropped.append(_label(model))
            except Exception:
                pass
    else:
        for model in model_list:
            try:
                await conn.execute_query(
                    f"DROP TABLE IF EXISTS {_sql_ref(model, engine)} CASCADE"
                )
                dropped.append(_label(model))
            except Exception:
                pass

    await Tortoise.close_connections()
    return dropped


async def _truncate_all(config: dict) -> list[str]:
    from tortoise import Tortoise

    await Tortoise.init(config=config)
    conn = Tortoise.get_connection("default")
    engine = _detect_engine(config)

    def _sql_ref(model, eng: str = "postgres") -> str:
        schema = getattr(model._meta, "schema", None)
        table = model._meta.db_table
        if eng == "mysql":
            return f"`{table}`"
        return f'"{schema}"."{table}"' if schema else f'"{table}"'

    def _label(model) -> str:
        schema = getattr(model._meta, "schema", None)
        table = model._meta.db_table
        return f"{schema}.{table}" if schema else table

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
                await conn.execute_query(f"TRUNCATE TABLE {_sql_ref(model, engine)}")
                truncated.append(_label(model))
            except Exception:
                pass
        await conn.execute_query("SET FOREIGN_KEY_CHECKS = 1")
    elif engine == "sqlite":
        for model in model_list:
            try:
                await conn.execute_query(f"DELETE FROM {_sql_ref(model, engine)}")
                truncated.append(_label(model))
            except Exception:
                pass
    else:
        for model in model_list:
            try:
                await conn.execute_query(
                    f"TRUNCATE TABLE {_sql_ref(model, engine)} RESTART IDENTITY CASCADE"
                )
                truncated.append(_label(model))
            except Exception:
                pass

    tables = truncated

    await Tortoise.close_connections()
    return tables


def run(config_path: str = "forgeapi.toml", force: bool = False) -> None:
    cfg = load_config(config_path)
    orm_path = cfg.database.tortoise_orm

    cwd = str(Path.cwd())
    if cwd not in sys.path:
        sys.path.insert(0, cwd)

    module_path, var_name = orm_path.rsplit(".", 1)
    try:
        mod = importlib.import_module(module_path)
        user_config: dict = getattr(mod, var_name)
    except (ImportError, AttributeError) as exc:
        typer.echo(f"Error: cannot import {orm_path}: {exc}", err=True)
        raise typer.Exit(code=1)

    if force:
        typer.echo(
            "WARNING: --force will DROP all tables (structure + data).\n"
            "You will need to run migrations again before the app can start.",
            err=False,
        )
        typer.confirm("This will DROP all tables. Continue?", abort=True)
        tables = asyncio.run(_drop_all(user_config))
        for table in tables:
            typer.echo(f"  dropped: {table}")
        typer.echo(f"\nDone — {len(tables)} table(s) dropped.")
    else:
        typer.confirm("This will TRUNCATE all tables (data only). Continue?", abort=True)
        tables = asyncio.run(_truncate_all(user_config))
        for table in tables:
            typer.echo(f"  truncated: {table}")
        typer.echo(f"\nDone — {len(tables)} table(s) cleared.")
