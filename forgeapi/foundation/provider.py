from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import FastAPI
    from forgeapi.config import KitConfig


class Provider:
    """Base class for module providers — Laravel Service Provider equivalent.

    ``Core`` only orchestrates: it collects providers, calls ``register()``
    on all of them, then ``boot()`` on all of them.  Module wiring logic
    lives in the module's own provider, not in ``Core``.

    Phases:

    * :meth:`register` — configure the module itself: facades, singletons,
      middleware.  Must NOT import user code — other modules may not be
      registered yet.
    * :meth:`boot` — runs after every provider has registered.  Discovery
      that imports user code (controllers, listeners, policies, models)
      belongs here, so user modules see fully configured facades at
      import time.

    Custom provider example::

        from forgeapi.foundation import Provider

        class TenantProvider(Provider):
            def register(self) -> None:
                self.app.add_middleware(TenantMiddleware)

            def boot(self) -> None:
                load_tenants(self.config.structure.models_dir)
    """

    def __init__(self, app: "FastAPI", config: "KitConfig") -> None:
        self.app = app
        self.config = config

    def register(self) -> None:
        """Configure the module. Runs before any provider boots."""

    def boot(self) -> None:
        """Run after all providers are registered. User-code imports go here."""


def import_string(dotted_path: str):
    """Import ``"app.models.User"`` → the ``User`` class.

    Raises:
        ForgeAPIConfigError: On an invalid path or failed import.
    """
    import importlib

    from forgeapi.exceptions import ForgeAPIConfigError

    module_path, _, attr = dotted_path.rpartition(".")
    if not module_path:
        raise ForgeAPIConfigError(
            f"Invalid import path '{dotted_path}'.",
            hint='Use a full dotted path, e.g. "app.models.User".',
        )
    try:
        module = importlib.import_module(module_path)
        return getattr(module, attr)
    except (ImportError, AttributeError) as exc:
        raise ForgeAPIConfigError(
            f"Cannot import '{dotted_path}': {exc}",
            hint="Check the dotted path in your config.",
        ) from exc
