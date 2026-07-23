import importlib.util
from pathlib import Path

from pydantic import ValidationError

from .models import KitConfig

__all__ = ["load_config"]


def load_config(path: str = "") -> KitConfig:
    """Load application config from a ``config/`` directory of Python dict files.

    Each ``config/<section>.py`` file must define a module-level ``config``
    dict; the filename becomes the section name::

        # config/auth.py
        from forgeapi import env

        config = {
            "default": "api",
            "guards": {
                "api": {"strategy": "cookie", "secret": env("COOKIE_SECRET")},
            },
        }

    Unknown sections (e.g. ``config/services.py``) are kept and reachable
    via :meth:`KitConfig.get`.

    Args:
        path: Config directory override.  Default: ``config/`` in cwd;
              pure defaults when the directory does not exist.
    """
    from forgeapi.exceptions import ForgeAPIConfigError

    if path and Path(path).suffix == ".toml":
        raise ForgeAPIConfigError(
            "forgeapi.toml is no longer supported.",
            hint=(
                "Migrate to a config/ directory of Python dict files "
                "(config/project.py, config/auth.py, ...). "
                "Run 'forgeapi init' in a scratch dir to see the format."
            ),
        )

    directory = Path(path) if path else Path("config")
    if directory.is_dir():
        return _from_py_dir(directory)
    return KitConfig()


def _from_py_dir(directory: Path) -> KitConfig:
    from forgeapi.exceptions import ForgeAPIConfigError

    raw: dict[str, dict] = {}
    for f in sorted(directory.glob("*.py")):
        if f.name.startswith("_"):
            continue
        raw[f.stem] = _load_section(f)

    try:
        cfg = KitConfig(**raw)
        cfg._provided = set(raw)
        return cfg
    except ValidationError as exc:
        raise ForgeAPIConfigError(
            f"Invalid configuration in '{directory}': {exc}",
            hint="Check your config for incorrect types or missing required fields.",
        ) from exc


def _load_section(file: Path) -> dict:
    from forgeapi.exceptions import ForgeAPIConfigError

    spec = importlib.util.spec_from_file_location(f"_forgeapi_config.{file.stem}", file)
    if spec is None or spec.loader is None:
        raise ForgeAPIConfigError(f"Cannot load config file '{file}'.")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        raise ForgeAPIConfigError(
            f"Error executing config file '{file}': {exc}",
            hint="Config files are plain Python — check the traceback above.",
        ) from exc

    section = getattr(module, "config", None)
    if not isinstance(section, dict):
        # config/database.py: a bare TORTOISE_ORM dict is enough — the dotted
        # import path the tortoise CLI needs is derived from the file location.
        # An explicit `config` dict overrides this (ORM dict living elsewhere).
        if file.stem == "database" and isinstance(getattr(module, "TORTOISE_ORM", None), dict):
            return {"tortoise_orm": f"{file.parent.name}.{file.stem}.TORTOISE_ORM"}
        raise ForgeAPIConfigError(
            f"Config file '{file}' must define a module-level 'config' dict.",
            hint='Example: config = {"default": "api", "guards": {...}}',
        )
    return section
