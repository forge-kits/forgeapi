from __future__ import annotations

import importlib
import sys
from pathlib import Path


def run(config_path: str = "forgeapi.toml") -> None:
    import typer
    from forgeapi.config import load_config

    cfg = load_config(config_path)
    st = cfg.structure

    cwd = str(Path.cwd())
    if cwd not in sys.path:
        sys.path.insert(0, cwd)

    models_dir = Path(st.models_dir)
    if not models_dir.exists():
        typer.echo(f"Models directory not found: {models_dir}")
        return

    try:
        from tortoise.models import Model as TortoiseModel
    except ImportError:
        typer.echo("Error: tortoise-orm not installed.", err=True)
        raise typer.Exit(code=1)

    found: list[tuple[str, str, list[str]]] = []

    for f in sorted(models_dir.glob("*.py")):
        if f.name.startswith("_"):
            continue
        try:
            rel = f.relative_to(Path.cwd())
        except ValueError:
            rel = f
        module_path = rel.with_suffix("").as_posix().replace("/", ".")

        try:
            mod = importlib.import_module(module_path)
        except Exception as exc:
            typer.echo(f"  warning  {module_path}: {exc}", err=True)
            continue

        for attr_name, obj in vars(mod).items():
            if (
                isinstance(obj, type)
                and issubclass(obj, TortoiseModel)
                and obj is not TortoiseModel
                and obj.__module__ == mod.__name__
                and not getattr(getattr(obj, "Meta", None), "abstract", False)
            ):
                table = getattr(getattr(obj, "Meta", None), "table", attr_name.lower() + "s")
                fields = list(obj._meta.fields_map.keys()) if hasattr(obj, "_meta") else []
                found.append((attr_name, table, fields))

    if not found:
        typer.echo("No models found.")
        return

    typer.echo("")
    for name, table, fields in found:
        typer.echo(f"  {name}  (table: {table})")
        for field in fields:
            typer.echo(f"    - {field}")
        typer.echo("")
    typer.echo(f"  {len(found)} model(s) total")
    typer.echo("")
