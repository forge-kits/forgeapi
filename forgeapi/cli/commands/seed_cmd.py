from __future__ import annotations

import asyncio
import importlib
import importlib.util
import re
import sys
from pathlib import Path


def _to_snake(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


async def _connect(cfg) -> None:
    from tortoise import Tortoise
    module_dotted, attr = cfg.database.tortoise_orm.rsplit(".", 1)
    mod = importlib.import_module(module_dotted)
    tortoise_config = getattr(mod, attr)
    await Tortoise.init(config=tortoise_config)


async def _execute(files: list[Path]) -> None:
    import typer
    from forgeapi.database import Seeder

    for f in files:
        spec = importlib.util.spec_from_file_location(f"_seed_{f.stem}", f)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        seeder_cls = next(
            (obj for _, obj in vars(mod).items()
             if isinstance(obj, type) and issubclass(obj, Seeder) and obj is not Seeder),
            None,
        )
        if seeder_cls is None:
            typer.echo(f"  skip     {f.name}  (no Seeder subclass)")
            continue

        typer.echo(f"  running  {seeder_cls.__name__}...")
        await seeder_cls().run()
        typer.echo(f"  done     {seeder_cls.__name__}")


def run(names: list[str], config_path: str = "forgeapi.toml") -> None:
    import typer
    from forgeapi.config import load_config

    cfg = load_config(config_path)
    seeds_dir = Path(cfg.structure.seeds_dir)

    cwd = str(Path.cwd())
    if cwd not in sys.path:
        sys.path.insert(0, cwd)

    if not seeds_dir.exists():
        typer.echo(f"Error: seeds directory '{seeds_dir}' not found.", err=True)
        raise typer.Exit(code=1)

    if names:
        files: list[Path] = []
        for name in names:
            class_name = name[0].upper() + name[1:]
            f = seeds_dir / f"{_to_snake(class_name)}_seeder.py"
            if not f.exists():
                typer.echo(f"Error: seeder not found: {f}", err=True)
                raise typer.Exit(code=1)
            files.append(f)
    else:
        files = sorted(seeds_dir.glob("*_seeder.py"))

    if not files:
        typer.echo("No seeders found.")
        return

    async def _main() -> None:
        await _connect(cfg)
        try:
            await _execute(files)
        finally:
            from tortoise import Tortoise
            await Tortoise.close_connections()

    typer.echo("")
    asyncio.run(_main())
    typer.echo("")
    typer.echo("Done.")


def make(name: str, config_path: str = "forgeapi.toml") -> None:
    """Generate a seeder file."""
    import typer
    from pathlib import Path
    from jinja2 import Environment, FileSystemLoader
    from forgeapi.config import load_config

    cfg = load_config(config_path)
    seeds_dir = Path(cfg.structure.seeds_dir)

    class_name = name[0].upper() + name[1:]
    module_name = _to_snake(class_name)

    templates_dir = Path(__file__).parent.parent / "templates"
    env = Environment(loader=FileSystemLoader(str(templates_dir)), keep_trailing_newline=True)
    content = env.get_template("seeder.py.jinja2").render(class_name=class_name)

    out = seeds_dir / f"{module_name}_seeder.py"
    if out.exists():
        typer.echo(f"  exists   {out}")
        return
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(content, encoding="utf-8")
    typer.echo(f"  created  {out}")
    typer.echo("Done.")
