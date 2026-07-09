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


async def _run_seeder(cls, name: str) -> None:
    import typer
    typer.echo(f"  running  {name}...")
    await cls().execute()
    typer.echo(f"  done     {name}")


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

        await _run_seeder(seeder_cls, seeder_cls.__name__)


async def _execute_from_init(seeds_dir: Path) -> None:
    import typer
    from forgeapi.database import Seeder

    init_file = seeds_dir / "__init__.py"
    spec = importlib.util.spec_from_file_location("_seeds_pkg", init_file)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    names = getattr(mod, "__all__", None)
    if not names:
        typer.echo("  __init__.py has no __all__ — nothing to run.")
        return

    for name in names:
        cls = getattr(mod, name, None)
        if cls is None or not (isinstance(cls, type) and issubclass(cls, Seeder) and cls is not Seeder):
            typer.echo(f"  skip     {name}  (not a Seeder subclass)")
            continue
        await _run_seeder(cls, name)


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

        async def _main() -> None:
            await _connect(cfg)
            try:
                await _execute(files)
            finally:
                from tortoise import Tortoise
                await Tortoise.close_connections()
    else:
        init_file = seeds_dir / "__init__.py"

        if not init_file.exists():
            typer.echo(
                f"Error: '{seeds_dir}/__init__.py' not found. "
                "Create it and define __all__ with the seeders to run.",
                err=True,
            )
            raise typer.Exit(code=1)

        async def _main() -> None:
            await _connect(cfg)
            try:
                await _execute_from_init(seeds_dir)
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
