from .kit import Core
from .foundation import Provider
from .config import KitConfig, load_config, env
from .exceptions import ForgeAPIError, ForgeAPIConfigError, ForgeAPIImportError
from .settings import BaseAppSettings
from .schemas import BaseSchema, BaseCreateSchema, BaseUpdateSchema
from .database import ModelMixin
from .events import Event, EventBus, listen, RedisBus
from .controllers import Controller, route
from .middleware import Middleware, Guard
from .logging import Log
from .policies import Policy, gate
from .support import Number, Str, Time
from .cache import Cache

__all__ = [
    # Facade
    "Core",
    "Provider",
    "KitConfig",
    "load_config",
    "env",
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
    # Database
    "ModelMixin",
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
    # Logging
    "Log",
    # Policies
    "Policy",
    "gate",
    # Support
    "Number",
    "Str",
    "Time",
    # Cache
    "Cache",
]


def __getattr__(name: str):
    _auth_exports = {
        "auth", "Auth", "guard", "Guard",
        "CurrentUser", "OptionalUser",
        "AuthUser", "TelegramUser",
        "JWTStrategy", "CookieStrategy", "TelegramStrategy",
    }
    _db_exports = {
        "Paginator", "Pagination",
        "CursorPaginator", "CursorPagination",
        "PaginatedResponse", "CursorResponse",
        "PaginationMeta", "PaginationLinks", "CursorMeta",
    }

    if name in _auth_exports:
        try:
            from . import auth as _auth_module
        except ImportError:
            raise ImportError(
                f"'{name}' requires PyJWT. Install it: pip install forge-kits[auth]"
            )
        return getattr(_auth_module, name)

    if name in _db_exports:
        try:
            from .pagination import (  # noqa: F401
                Paginator, Pagination,
                CursorPaginator, CursorPagination,
                PaginatedResponse, CursorResponse,
                PaginationMeta, PaginationLinks, CursorMeta,
            )
        except ImportError:
            raise ImportError(
                f"'{name}' requires tortoise-orm. Install it: pip install forge-kits[db]"
            )
        return locals()[name]

    raise AttributeError(f"module 'forgeapi' has no attribute '{name}'")
