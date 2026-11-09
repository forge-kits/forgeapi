"""Discovery of project-defined CLI commands (``forgeapi make:command``)."""
from __future__ import annotations

import importlib
import inspect
import sys
from pathlib import Path

from forgeapi.cli.base import Command


def discover(commands_dir: str) -> tuple[list[Command], list[str]]:
    """Import every module in *commands_dir* and instantiate its ``Command`` subclasses.

    Must run from the project root (the CLI changes there first).  Returns
    ``(commands, errors)``: a module that fails to import is reported in *errors* and
    skipped, so one broken file never hides the other commands.
    """
    directory = Path(commands_dir)
    if not directory.is_dir():
        return [], []

    cwd = str(Path.cwd())
    if cwd not in sys.path:
        sys.path.insert(0, cwd)

    package = ".".join(directory.parts)
    commands: list[Command] = []
    errors: list[str] = []
    for file in sorted(directory.glob("*.py")):
        if file.name.startswith("_"):
            continue
        module_name = f"{package}.{file.stem}"
        try:
            module = importlib.import_module(module_name)
        except Exception as exc:
            errors.append(f"{file}: {type(exc).__name__}: {exc}")
            continue
        for _, obj in inspect.getmembers(module, inspect.isclass):
            if issubclass(obj, Command) and obj is not Command and obj.__module__ == module_name and obj.name:
                commands.append(obj())
    return commands, errors
