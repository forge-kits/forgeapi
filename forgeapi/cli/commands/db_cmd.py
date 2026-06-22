import subprocess
import sys
from pathlib import Path


_DB_SUBCOMMANDS = ("init", "makemigrations", "migrate", "downgrade", "history", "heads", "sqlmigrate")


def run(subcmd: str, extra_args: list[str], config_path: str = "forgeapi.toml") -> None:
    import typer
    from forgeapi.config import load_config

    if subcmd not in _DB_SUBCOMMANDS:
        typer.echo(f"Error: unknown db command 'db:{subcmd}'.", err=True)
        typer.echo(f"  Available: {', '.join(f'db:{s}' for s in _DB_SUBCOMMANDS)}", err=True)
        raise typer.Exit(code=1)

    cfg = load_config(config_path)
    orm_path = cfg.database.tortoise_orm

    tortoise_bin = Path(sys.executable).parent / "tortoise"
    if not tortoise_bin.exists():
        typer.echo("Error: tortoise binary not found. Install tortoise-orm.", err=True)
        raise typer.Exit(code=1)

    cmd = [str(tortoise_bin), "-c", orm_path, subcmd] + extra_args
    result = subprocess.run(cmd)
    sys.exit(result.returncode)
