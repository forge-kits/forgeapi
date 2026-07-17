import importlib
import sys
from pathlib import Path

from forgeapi.exceptions import ForgeAPIConfigError
from forgeapi.logging import log

from .mixins import PermissionsMixin

_log = log.channel("permissions.discovery")


def find_permissions_model(models_dir: str, *, required: bool = True) -> type | None:
    """Scan *models_dir* for the single model that inherits ``PermissionsMixin``.

    Args:
        required: When ``False``, a missing directory or absent model returns
            ``None`` instead of raising (convention mode — permissions are
            simply not active).

    Raises:
        ForgeAPIConfigError: If more than one model inherits the mixin, or —
            with ``required=True`` — the directory/model is missing.
    """
    directory = Path(models_dir)
    if not directory.exists():
        if not required:
            return None
        raise ForgeAPIConfigError(
            f"models_dir '{directory}' does not exist.",
            hint="Create the directory or update models_dir in config/structure.py.",
        )

    cwd = str(Path.cwd())
    if cwd not in sys.path:
        sys.path.insert(0, cwd)

    found: list[type] = []
    for f in sorted(directory.glob("*.py")):
        if f.name.startswith("_"):
            continue
        try:
            rel = f.relative_to(Path.cwd())
        except ValueError:
            rel = f
        module_path = rel.with_suffix("").as_posix().replace("/", ".")
        try:
            mod = importlib.import_module(module_path)
        except Exception:
            continue
        for _, obj in vars(mod).items():
            if (
                isinstance(obj, type)
                and issubclass(obj, PermissionsMixin)
                and obj is not PermissionsMixin
                and obj.__module__ == mod.__name__
            ):
                found.append(obj)

    if not found:
        if not required:
            return None
        raise ForgeAPIConfigError(
            f"No model with PermissionsMixin found in '{directory}'.",
            hint="Add PermissionsMixin to your User model.",
        )
    if len(found) > 1:
        names = ", ".join(c.__name__ for c in found)
        raise ForgeAPIConfigError(
            f"Multiple PermissionsMixin models found: {names}.",
            hint="Only one model may inherit PermissionsMixin.",
        )

    _log.debug("Permissions: auto-detected model '%s'", found[0].__name__)
    return found[0]
