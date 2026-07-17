import importlib
import sys
from pathlib import Path

from fastapi import FastAPI

from forgeapi.logging import log

_log = log.channel("controllers.discovery")


def load_controllers(app: FastAPI, controllers_dir: str, base_prefix: str = "") -> None:
    """Auto-import ``**/*_controller.py`` from *controllers_dir* and register routers.

    Supports two styles:

    * ``Controller`` subclasses with ``@route`` decorators (preferred);
    * legacy modules exposing a module-level ``router``.
    """
    directory = Path(controllers_dir)
    if not directory.exists():
        return

    cwd = str(Path.cwd())
    if cwd not in sys.path:
        sys.path.insert(0, cwd)

    from .base import Controller as BaseController

    for f in sorted(directory.glob("**/*_controller.py")):
        try:
            rel = f.relative_to(Path.cwd())
        except ValueError:
            rel = f
        module_path = rel.with_suffix("").as_posix().replace("/", ".")
        try:
            mod = importlib.import_module(module_path)
        except Exception as exc:
            _log.error("Failed to load controller '%s': %s", f, exc, exc_info=exc)
            continue

        # New style: Controller subclasses with @route decorators
        ctrl_classes = [
            obj for _, obj in vars(mod).items()
            if isinstance(obj, type)
            and issubclass(obj, BaseController)
            and obj is not BaseController
            and obj.__module__ == mod.__name__
        ]
        if ctrl_classes:
            for cls in ctrl_classes:
                if not cls._registered:
                    cls()
                app.include_router(cls.router, prefix=base_prefix)
            continue

        # Legacy style: module-level router
        router = getattr(mod, "router", None)
        if router is None:
            continue
        if not router.routes:
            for attr_name, obj in vars(mod).items():
                if (
                    isinstance(obj, type)
                    and attr_name.endswith("Controller")
                    and obj.__module__ == mod.__name__
                ):
                    obj()
        app.include_router(router, prefix=base_prefix)
