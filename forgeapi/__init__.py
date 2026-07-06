from .kit import Core
from .config import KitConfig, load_config
from .exceptions import ForgeAPIError, ForgeAPIConfigError, ForgeAPIImportError
from .settings import BaseAppSettings
from .schemas import BaseSchema, BaseCreateSchema, BaseUpdateSchema
from .events import Event, EventBus, listen, RedisBus
from .controllers import Controller, route
from .middleware import Middleware, Guard

__all__ = [
    # Facade
    "Core",
    "KitConfig",
    "load_config",
    # Exceptions
    "ForgeAPIError",
    "ForgeAPIConfigError",
    "ForgeAPIImportError",
    # Settings
    "BaseAppSettings",
    # Schemas
    "BaseSchema",
    "BaseCreateSchema",
    "BaseUpdateSchema",
    # Events
    "Event",
    "EventBus",
    "listen",
    "RedisBus",
    # Controllers
    "Controller",
    "route",
    # Middleware
    "Middleware",
    "Guard",
]


def __getattr__(name: str):
    _auth_exports = {
        "AuthBackend", "CurrentUser", "OptionalUser",
        "JWTStrategy", "CookieStrategy", "TelegramStrategy",
    }
    _db_exports = {"Paginator", "Pagination"}

    if name in _auth_exports:
        try:
            from .auth import (  # noqa: F401
                AuthBackend, CurrentUser, OptionalUser,
                JWTStrategy, CookieStrategy, TelegramStrategy,
            )
        except ImportError:
            raise ImportError(
                f"'{name}' requires PyJWT. Install it: pip install forge-kits[auth]"
            )
        return locals()[name]

    if name in _db_exports:
        try:
            from .pagination import Paginator, Pagination  # noqa: F401
        except ImportError:
            raise ImportError(
                f"'{name}' requires tortoise-orm. Install it: pip install forge-kits[db]"
            )
        return locals()[name]

    raise AttributeError(f"module 'forgeapi' has no attribute '{name}'")
