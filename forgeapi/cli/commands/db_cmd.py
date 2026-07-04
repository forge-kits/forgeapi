import os
import shutil
import subprocess
import sys
from pathlib import Path


_DB_SUBCOMMANDS = ("init", "makemigrations", "migrate", "downgrade", "history", "heads", "sqlmigrate")


def _find_tortoise_bin() -> str | None:
    # Prefer the binary next to the current Python interpreter (respects venvs).
    # On Windows scripts live in Scripts\ and carry a .exe suffix.
    candidates = ["tortoise", "tortoise.exe"]
    scripts_dir = Path(sys.executable).parent
    for name in candidates:
        path = scripts_dir / name
        if path.exists():
            return str(path)

    # Fall back to PATH lookup (handles global installs and unusual venv layouts).
    found = shutil.which("tortoise")
    return found


def run(subcmd: str, extra_args: list[str], config_path: str = "forgeapi.toml") -> None:
    import typer
    from forgeapi.config import load_config

    if subcmd not in _DB_SUBCOMMANDS:
        typer.echo(f"Error: unknown db command 'db:{subcmd}'.", err=True)
        typer.echo(f"  Available: {', '.join(f'db:{s}' for s in _DB_SUBCOMMANDS)}", err=True)
        raise typer.Exit(code=1)

    cfg = load_config(config_path)
    orm_path = cfg.database.tortoise_orm

    tortoise_bin = _find_tortoise_bin()
    if tortoise_bin is None:
        typer.echo("Error: tortoise binary not found. Install tortoise-orm.", err=True)
        raise typer.Exit(code=1)

    cmd = [tortoise_bin, "-c", orm_path, subcmd] + extra_args
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    result = subprocess.run(cmd, env=env)
    sys.exit(result.returncode)
