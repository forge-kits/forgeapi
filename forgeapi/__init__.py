from .kit import Core
from .config import KitConfig, load_config
from .settings import BaseAppSettings
from .schemas import BaseSchema, BaseCreateSchema, BaseUpdateSchema
from .events import Event, EventBus, listen
from .controllers import Controller, route
from .middleware import Middleware, Guard

__all__ = [
    # Facade
    "Core",
    "KitConfig",
    "load_config",
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
            from .auth import (
                AuthBackend, CurrentUser, OptionalUser,
                JWTStrategy, CookieStrategy, TelegramStrategy,
            )
        except ImportError:
            raise ImportError(
                f"'{name}' requires PyJWT. Install it: pip install forgeapi[auth]"
            )
        return locals()[name]

    if name in _db_exports:
        try:
            from .pagination import Paginator, Pagination
        except ImportError:
            raise ImportError(
                f"'{name}' requires tortoise-orm. Install it: pip install forgeapi[db]"
            )
        return locals()[name]

    raise AttributeError(f"module 'forgeapi' has no attribute '{name}'")
