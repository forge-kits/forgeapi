from __future__ import annotations

import importlib
import sys
from pathlib import Path

from forgeapi.cli.base import Command


class RoutersCommand(Command):
    name = "routers"
    help_text = """\
Usage: forgeapi routers

Scans all controllers in controllers_dir and prints every registered route.
Does not require a running database — reads route metadata at import time.

Output:
  METHOD  PATH                             HANDLER
  GET     /api/v1/users/                   UserController.index
  POST    /api/v1/users/register           UserController.register
  ...
"""

    def handle(self, cmd: str, args: list[str]) -> None:
        import typer
        from forgeapi.config import load_config

        cfg = load_config()
        st = cfg.structure

        cwd = str(Path.cwd())
        if cwd not in sys.path:
            sys.path.insert(0, cwd)

        directory = Path(st.controllers_dir)
        if not directory.exists():
            typer.echo(f"Controllers directory not found: {directory}")
            return

        from forgeapi.controllers.base import Controller as BaseController

        base_prefix = st.base_prefix
        routes: list[tuple[str, str, str, str]] = []

        for f in sorted(directory.glob("**/*_controller.py")):
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

            ctrl_classes = [
                obj for _, obj in vars(mod).items()
                if isinstance(obj, type)
                and issubclass(obj, BaseController)
                and obj is not BaseController
                and obj.__module__ == mod.__name__
            ]

            for cls in ctrl_classes:
                for method_name in dir(cls):
                    if method_name.startswith("_"):
                        continue
                    fn = getattr(cls, method_name)
                    if callable(fn) and hasattr(fn, "_route"):
                        meta = fn._route
                        full_path = base_prefix + cls.prefix + meta["path"]
                        for http_method in meta["methods"]:
                            routes.append((http_method, full_path, cls.__name__, method_name))

        if not routes:
            typer.echo("No routes found.")
            return

        routes.sort(key=lambda r: (r[1], r[0]))

        col_method = max(len(r[0]) for r in routes)
        col_path   = max(len(r[1]) for r in routes)

        typer.echo("")
        typer.echo(f"  {'METHOD':<{col_method}}  {'PATH':<{col_path}}  HANDLER")
        typer.echo("  " + "-" * (col_method + col_path + 14))
        for method, path, cls_name, fn_name in routes:
            typer.echo(f"  {method:<{col_method}}  {path:<{col_path}}  {cls_name}.{fn_name}")
        typer.echo("")
        typer.echo(f"  {len(routes)} route(s) total")
        typer.echo("")
