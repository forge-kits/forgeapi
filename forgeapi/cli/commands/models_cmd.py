from __future__ import annotations

import importlib
import sys
from pathlib import Path

from forgeapi.cli.base import Command


class ModelsCommand(Command):
    name = "models"
    help_text = """\
Usage: forgeapi models

Lists all Tortoise model classes found in models_dir, their table names
and field names.
"""

    def handle(self, cmd: str, args: list[str]) -> None:
        from forgeapi.cli import ui
        from forgeapi.config import load_config

        cfg = load_config()
        st = cfg.structure

        cwd = str(Path.cwd())
        if cwd not in sys.path:
            sys.path.insert(0, cwd)

        models_dir = Path(st.models_dir)
        if not models_dir.exists():
            ui.warn(f"Models directory not found: {models_dir}")
            return

        try:
            from tortoise.models import Model as TortoiseModel
        except ImportError:
            self.abort("tortoise-orm not installed.")

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
                ui.warn(f"{module_path}: {exc}", stderr=True)
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
            ui.info("No models found.")
            return

        ui.blank()
        for name, table, fields in found:
            ui.dotted(name, table)
            ui.indented(", ".join(fields))
        ui.blank()
        ui.console.print(f"  Showing [{len(found)}] models", style="dim", markup=False)
        ui.blank()
