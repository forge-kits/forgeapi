from __future__ import annotations

import asyncio
import importlib
import importlib.util
import re
import sys
from pathlib import Path

from forgeapi.cli.base import Command


class SeedCommand(Command):
    name = "db:seed"

    def handle(self, cmd: str, args: list[str]) -> None:
        import typer
        from forgeapi.config import load_config

        cfg = load_config()
        seeds_dir = Path(cfg.structure.seeds_dir)

        cwd = str(Path.cwd())
        if cwd not in sys.path:
            sys.path.insert(0, cwd)

        if not seeds_dir.exists():
            self.abort(f"seeds directory '{seeds_dir}' not found.")

        names = [a for a in args if not a.startswith("-")]

        if names:
            files: list[Path] = []
            for name in names:
                class_name = name[0].upper() + name[1:]
                f = seeds_dir / f"{self._to_snake(class_name)}_seeder.py"
                if not f.exists():
                    self.abort(f"seeder not found: {f}")
                files.append(f)

            async def _main() -> None:
                await self._connect(cfg)
                try:
                    await self._execute(files)
                finally:
                    from tortoise import Tortoise
                    await Tortoise.close_connections()
        else:
            init_file = seeds_dir / "__init__.py"
            if not init_file.exists():
                self.abort(
                    f"'{seeds_dir}/__init__.py' not found. "
                    "Create it and define __all__ with the seeders to run."
                )

            async def _main() -> None:
                await self._connect(cfg)
                try:
                    await self._execute_from_init(seeds_dir)
                finally:
                    from tortoise import Tortoise
                    await Tortoise.close_connections()

        typer.echo("")
        asyncio.run(_main())
        typer.echo("")
        typer.echo("Done.")

    # ── Internals ───────────────────────────────────────────────────────────────

    @staticmethod
    def _to_snake(name: str) -> str:
        return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()

    @staticmethod
    async def _connect(cfg) -> None:
        module_dotted, attr = cfg.database.tortoise_orm.rsplit(".", 1)
        mod = importlib.import_module(module_dotted)
        tortoise_config = getattr(mod, attr)
        from tortoise import Tortoise
        await Tortoise.init(config=tortoise_config)

    @staticmethod
    async def _run_seeder(cls, name: str) -> None:
        import typer
        typer.echo(f"  running  {name}...")
        await cls().execute()
        typer.echo(f"  done     {name}")

    async def _execute(self, files: list[Path]) -> None:
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

            await self._run_seeder(seeder_cls, seeder_cls.__name__)

    async def _execute_from_init(self, seeds_dir: Path) -> None:
        import typer
        from forgeapi.database import Seeder

        init_file = seeds_dir / "__init__.py"
        pkg_name = "_seeds_pkg"

        for sibling in sorted(seeds_dir.glob("*.py")):
            if sibling.name == "__init__.py":
                continue
            sub_name = f"{pkg_name}.{sibling.stem}"
            if sub_name not in sys.modules:
                sib_spec = importlib.util.spec_from_file_location(sub_name, sibling)
                sib_mod = importlib.util.module_from_spec(sib_spec)
                sib_mod.__package__ = pkg_name
                sys.modules[sub_name] = sib_mod
                sib_spec.loader.exec_module(sib_mod)

        spec = importlib.util.spec_from_file_location(
            pkg_name, init_file, submodule_search_locations=[str(seeds_dir)]
        )
        mod = importlib.util.module_from_spec(spec)
        mod.__package__ = pkg_name
        sys.modules[pkg_name] = mod
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
            await self._run_seeder(cls, name)
