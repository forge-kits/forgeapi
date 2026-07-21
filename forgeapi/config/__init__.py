from .env import env
from .loader import load_config
from .models import (
    AuthConfig,
    CacheConfig,
    DatabaseConfig,
    HttpConfig,
    KitConfig,
    PaginationConfig,
    ProjectConfig,
    StorageConfig,
    StructureConfig,
)

__all__ = [
    "env",
    "load_config",
    "config_from_dict",
    "KitConfig",
    "ProjectConfig",
    "StructureConfig",
    "HttpConfig",
    "AuthConfig",
    "PaginationConfig",
    "DatabaseConfig",
    "CacheConfig",
    "StorageConfig",
]


def config_from_dict(data: dict) -> KitConfig:
    """Build :class:`KitConfig` from a plain Python dictionary.

    Useful when you want to configure Core programmatically without a
    ``config/`` directory::

        from forgeapi import config_from_dict, Core

        cfg = config_from_dict({
            "project": {"name": "My App"},
            "storage": {"driver": "s3", "bucket": "my-bucket"},
        })
        core = Core(app, config=cfg)
    """
    from pydantic import ValidationError
    from forgeapi.exceptions import ForgeAPIConfigError

    try:
        cfg = KitConfig(**data)
        cfg._provided = set(data.keys())
        return cfg
    except ValidationError as exc:
        raise ForgeAPIConfigError(
            f"Invalid config: {exc}",
            hint="Check your configuration dict for incorrect types.",
        ) from exc
