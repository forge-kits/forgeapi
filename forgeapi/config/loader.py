import importlib.util
from pathlib import Path

from pydantic import ValidationError

from .models import KitConfig, ProjectConfig

__all__ = ["load_config"]


def load_config(path: str = "") -> KitConfig:
    """Load the application config from ``config/app.py`` and ``config/database.py``.

    ``config/app.py`` defines a module-level ``config`` dict.  The project settings sit at
    the top level, every feature is a key of its own, and a feature is switched on by
    having its key::

        # config/app.py
        from forgeapi import env

        config = {
            "name": "demo",
            "debug": env("APP_DEBUG", False),

            "auth": {
                "default": "api",
                "guards": {"api": {"strategy": "cookie", "model": "database.models.user.User"}},
            },
            # "queue": {"queue": "default"},
        }

    A key that is not a project setting or a built-in section (``"services": {...}``) is kept
    and reachable via :meth:`KitConfig.get`.  ``config/database.py`` stays a separate file,
    it holds the ``TORTOISE_ORM`` dict the tortoise CLI imports.

    Args:
        path: Config directory override.  Default: ``config/`` in cwd;
              pure defaults when the directory does not exist.
    """
    from forgeapi.exceptions import ForgeAPIConfigError

    if path and Path(path).suffix == ".toml":
        raise ForgeAPIConfigError(
            "forgeapi.toml is no longer supported.",
            hint=(
                "Move the settings to config/app.py and config/database.py "
                "(Python dict files). Run 'forgeapi init' in a scratch dir to see the format."
            ),
        )

    directory = Path(path) if path else Path("config")
    if directory.is_dir():
        return _from_py_dir(directory)
    return KitConfig()


_FILES = ("app.py", "database.py")


def _from_py_dir(directory: Path) -> KitConfig:
    from forgeapi.exceptions import ForgeAPIConfigError

    stray = sorted(f.name for f in directory.glob("*.py") if f.name not in _FILES and not f.name.startswith("_"))
    if stray:
        raise ForgeAPIConfigError(
            f"{', '.join(f'config/{name}' for name in stray)} {'is' if len(stray) == 1 else 'are'} not read any more: "
            "all settings except the database live in config/app.py.",
            hint=(
                'Move them into config/app.py: the keys of project.py go to the top level, '
                'every other file becomes a key named after it, e.g. "auth": {...}, "mail": {...}. '
                "Run 'forgeapi init' in a scratch dir to see the layout."
            ),
        )

    raw: dict[str, dict] = {}
    app_file = directory / "app.py"
    if app_file.exists():
        raw.update(_split_app(_load_module_dict(app_file), app_file))
    database_file = directory / "database.py"
    if database_file.exists():
        raw["database"] = _load_database(database_file)

    try:
        cfg = KitConfig(**raw)
        cfg._provided = set(raw)
        return cfg
    except ValidationError as exc:
        raise ForgeAPIConfigError(
            f"Invalid configuration in '{directory}': {exc}",
            hint="Check your config for incorrect types or missing required fields.",
        ) from exc


def _split_app(config: dict, file: Path) -> dict[str, dict]:
    """The ``config/app.py`` dict as sections: the project keys form ``project``, the rest are sections."""
    from forgeapi.exceptions import ForgeAPIConfigError

    project_keys = set(ProjectConfig.model_fields)
    sections: dict[str, dict] = {}
    project: dict = {}
    for key, value in config.items():
        if key in project_keys:
            project[key] = value
        elif isinstance(value, dict):
            sections[key] = value
        else:
            raise ForgeAPIConfigError(
                f'Unknown key "{key}" in {file}.',
                hint=(
                    f"Project settings: {', '.join(sorted(project_keys))}. "
                    'A feature is a dict, e.g. "auth": {...}, "mail": {...}.'
                ),
            )
    if project:
        sections["project"] = project
    return sections


def _load_module(file: Path):
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
    return module


def _load_module_dict(file: Path) -> dict:
    from forgeapi.exceptions import ForgeAPIConfigError

    config = getattr(_load_module(file), "config", None)
    if not isinstance(config, dict):
        raise ForgeAPIConfigError(
            f"Config file '{file}' must define a module-level 'config' dict.",
            hint='Example: config = {"name": "demo", "auth": {...}}',
        )
    return config


def _load_database(file: Path) -> dict:
    """``config/database.py``: a bare ``TORTOISE_ORM`` dict is enough.

    The dotted import path the tortoise CLI needs is derived from the file location.
    An explicit ``config`` dict overrides this (the ORM dict living elsewhere).
    """
    from forgeapi.exceptions import ForgeAPIConfigError

    module = _load_module(file)
    section = getattr(module, "config", None)
    if isinstance(section, dict):
        return section
    if isinstance(getattr(module, "TORTOISE_ORM", None), dict):
        return {"tortoise_orm": f"{file.parent.name}.{file.stem}.TORTOISE_ORM"}
    raise ForgeAPIConfigError(
        f"Config file '{file}' must define a TORTOISE_ORM dict.",
        hint='Example: TORTOISE_ORM = {"connections": {...}, "apps": {...}}',
    )
