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


async def _truncate_all(config: dict) -> list[str]:
    from tortoise import Tortoise

    await Tortoise.init(config=config)
    conn = Tortoise.get_connection("default")
    engine = _detect_engine(config)

    tables = [
        model._meta.db_table
        for app_models in Tortoise.apps.values()
        for model in app_models.values()
        if model._meta.db_table not in _SKIP_TABLES
    ]

    if engine == "mysql":
        await conn.execute_query("SET FOREIGN_KEY_CHECKS = 0")
        for table in tables:
            await conn.execute_query(f"TRUNCATE TABLE `{table}`")
        await conn.execute_query("SET FOREIGN_KEY_CHECKS = 1")
    elif engine == "sqlite":
        for table in tables:
            await conn.execute_query(f'DELETE FROM "{table}"')
    else:
        joined = ", ".join(f'"{t}"' for t in tables)
        await conn.execute_query(f"TRUNCATE TABLE {joined} RESTART IDENTITY CASCADE")

    await Tortoise.close_connections()
    return tables


def run(config_path: str = "forgeapi.toml") -> None:
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

    typer.confirm("This will TRUNCATE all tables. Continue?", abort=True)

    tables = asyncio.run(_truncate_all(user_config))
    for table in tables:
        typer.echo(f"  truncated: {table}")
    typer.echo(f"\nDone — {len(tables)} table(s) cleared.")
