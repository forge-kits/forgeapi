from .bootstrap import Core
from .foundation import Provider
from .config import KitConfig, load_config, config_from_dict, env, StorageConfig
from .exceptions import ForgeAPIError, ForgeAPIConfigError, ForgeAPIImportError
from .settings import BaseAppSettings
from .schemas import BaseSchema, BaseCreateSchema, BaseUpdateSchema
from .database import ModelMixin, scope, ModelObserver
from .broadcasting import BroadcastManager, broadcast
from .controllers import Controller, route
from .middleware import Middleware, Guard
from .logging import Log
from .policies import Policy, gate
from .support import Number, Str, Time
from .cache import Cache
from .storage import Storage, ImageProcessor
from .scheduling import Scheduler, ScheduledTask
from .queue import Job, dispatch

__all__ = [
    # Core
    "Core",
    "Provider",
    # Config
    "KitConfig",
    "StorageConfig",
    "load_config",
    "config_from_dict",
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
    "scope",
    "ModelObserver",
    # Broadcasting
    "BroadcastManager",
    "broadcast",
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
    # Storage
    "Storage",
    "ImageProcessor",
    # Scheduling
    "Scheduler",
    "ScheduledTask",
    # Queue
    "Job",
    "dispatch",
]


def __getattr__(name: str):
    _auth_exports = {
        "auth", "Auth", "guard",
        "CurrentUser", "OptionalUser",
        "AuthUser", "TelegramUser",
        "CookieStrategy", "TelegramStrategy",
    }
    _db_exports = {
        "PaginatedResponse", "SimplePaginatedResponse", "CursorResponse",
        "PaginationMeta", "SimplePaginationMeta", "PaginationLinks", "CursorMeta",
    }

    if name in _auth_exports:
        import importlib
        _auth_module = importlib.import_module("forgeapi.auth")
        return getattr(_auth_module, name)

    if name in _db_exports:
        import importlib
        _pag = importlib.import_module("forgeapi.pagination")
        return getattr(_pag, name)

    raise AttributeError(f"module 'forgeapi' has no attribute '{name}'")
