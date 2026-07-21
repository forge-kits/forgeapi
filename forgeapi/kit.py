from fastapi import FastAPI

from .config import KitConfig, load_config
from .foundation import Provider
from .logging import log

_log = log.channel("core")


class Core:
    """Bootstrap a FastAPI application with forgeapi modules.

    The whole setup is config-driven — ``Core(app)`` is the entire wiring::

        from fastapi import FastAPI
        from forgeapi import Core

        app = FastAPI()
        Core(app)

    What runs is decided by the ``config/`` directory (convention over
    configuration):

    * middleware stack        — ``config/http.py`` (cors, rate_limit, ...)
    * auth guards             — boot when ``config/auth.py`` exists
    * storage                 — boot when ``config/storage.py`` exists
    * Telescope               — ``"debug": True`` in ``config/project.py``
    * permissions             — boot when a model in ``models_dir`` inherits ``PermissionsMixin``
    * controllers / listeners / policies — boot when their directory exists
    * pagination and cache    — always configured (from their sections or defaults)
    * custom providers        — ``"providers"`` in ``config/project.py``

    ``Core`` itself is a thin orchestrator: it collects module
    :class:`~forgeapi.foundation.Provider` instances, calls ``register()``
    on all, then ``boot()`` on all.  Module logic lives in each module's
    provider, never here.

    Args:
        app: The FastAPI application to configure.
        config: Optional pre-built :class:`~forgeapi.config.KitConfig`.
                When omitted, ``load_config()`` reads from ``config/``.
    """

    def __init__(self, app: FastAPI, *, config: "KitConfig | None" = None) -> None:
        self._app = app
        self._cfg: KitConfig = config or load_config()
        self._debug = self._cfg.project.debug

        if self._cfg.project.name:
            self._app.title = self._cfg.project.name
        if self._cfg.project.description:
            self._app.description = self._cfg.project.description

        self._providers: list[Provider] = self._collect_providers()

        for p in self._providers:
            p.register()
        for p in self._providers:
            p.boot()

    # ── Provider selection ────────────────────────────────────────────────────

    def _collect_providers(self) -> list[Provider]:
        app, cfg = self._app, self._cfg
        providers: list[Provider] = []
        add = providers.append

        if self._debug:
            from .telescope.provider import TelescopeProvider
            add(TelescopeProvider(app, cfg))

        from .middleware.provider import MiddlewareProvider
        add(MiddlewareProvider(app, cfg))

        from .pagination.provider import PaginationProvider
        add(PaginationProvider(app, cfg))

        if cfg.provided("auth"):
            from .auth.provider import AuthProvider
            add(AuthProvider(app, cfg))

        from .cache.provider import CacheProvider
        add(CacheProvider(app, cfg))

        if cfg.provided("storage"):
            from .storage.provider import StorageProvider
            add(StorageProvider(app, cfg))

        from .events.provider import EventProvider
        add(EventProvider(app, cfg))

        from .policies.provider import PolicyProvider
        add(PolicyProvider(app, cfg))

        from .permissions.provider import PermissionProvider
        add(PermissionProvider(app, cfg))

        from .controllers.provider import ControllerProvider
        add(ControllerProvider(app, cfg))

        for provider_cls in cfg.project.providers:
            add(provider_cls(app, cfg))

        return providers

    # ── Middleware ────────────────────────────────────────────────────────────

    def use(self, middleware_cls, **kwargs) -> "Core":
        """Register a custom global middleware after Core is created.

        Args:
            middleware_cls: A :class:`~forgeapi.middleware.Middleware` subclass
                (or any Starlette-compatible middleware class).
            **kwargs: Extra keyword arguments passed to the middleware constructor.

        Returns:
            ``self`` for chaining.

        Example::

            core.use(TimingMiddleware)
            core.use(TenantMiddleware, default_tenant="acme")
        """
        self._app.add_middleware(middleware_cls, **kwargs)
        return self

    # ── Router ────────────────────────────────────────────────────────────────

    def include_router(self, router, prefix: str = "", **kwargs) -> "Core":
        """Include a router, prepending the configured ``base_prefix``."""
        base = self._cfg.structure.base_prefix
        self._app.include_router(router, prefix=base + prefix, **kwargs)
        return self

    # ── Properties ────────────────────────────────────────────────────────────

    @property
    def auth(self):
        """The global :class:`~forgeapi.auth.facade.Auth` facade, or ``None`` if auth was not enabled."""
        from .auth.facade import auth as _auth_facade
        return _auth_facade if _auth_facade.is_configured else None

    @property
    def config(self) -> KitConfig:
        """Loaded :class:`~forgeapi.config.KitConfig`."""
        return self._cfg

    @property
    def providers(self) -> list[Provider]:
        """Providers that were registered and booted, in order."""
        return list(self._providers)
