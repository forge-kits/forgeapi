import logging
import os

from fastapi import FastAPI

from .config import KitConfig, load_config
from .exceptions import ForgeAPIConfigError, ForgeAPIImportError
from .middleware.cors import add_cors
from .middleware.rate_limit import RateLimitMiddleware
from .middleware.request_id import RequestIDMiddleware
from .middleware.logging import LoggingMiddleware
from .pagination.paginator import Paginator

logger = logging.getLogger("forgeapi.core")


class Core:
    """Configure a FastAPI application with forgeapi modules.

    All options are keyword-only.  ``logging`` and ``controllers`` are enabled
    by default and can be omitted.

    Args:
        app:         The FastAPI application to configure.
        auth:        ``True`` → strategy from ``forgeapi.toml``; ``"jwt"`` /
                     ``"cookie"`` / ``"telegram"`` → override strategy;
                     ``False`` → skip (default).
        cors:        ``True`` → allow all origins; list of origins → allow
                     specific origins; ``False`` → skip (default).
        rate_limit:  ``True`` → 60 req/min; ``int`` → custom limit;
                     ``False`` → skip (default).
        pagination:  ``True`` → limits from ``forgeapi.toml``; ``int`` →
                     default_limit override; ``False`` → skip (default).
        request_id:  Inject ``X-Request-ID`` header. Default ``False``.
        events:      Auto-load listeners from ``listeners_dir``. Default ``False``.
        logging:     Log each request (method, path, status, duration). Default ``True``.
        controllers: Auto-import ``*_controller.py`` and register routers. Default ``True``.
        config_path: Path to ``forgeapi.toml``. Default ``"forgeapi.toml"``.

    Example::

        from fastapi import FastAPI
        from forgeapi import Core

        app = FastAPI()

        core = Core(
            app,
            auth=True,
            cors=["*"],
            rate_limit=60,
            pagination=20,
            request_id=True,
            events=True,
        )
    """

    def __init__(
        self,
        app: FastAPI,
        *,
        auth: bool | str = False,
        cors: bool | list[str] = False,
        rate_limit: bool | int = False,
        pagination: bool | int = False,
        request_id: bool = False,
        events: bool = False,
        logging: bool = True,
        controllers: bool = True,
        permissions: "bool | type | None" = None,
        middleware: list | None = None,
        debug: bool = False,
        config_path: str = "forgeapi.toml",
    ) -> None:
        self._app = app
        self._cfg: KitConfig = load_config(config_path)
        self._auth = None
        self._debug = debug

        if debug:
            logger.warning(
                "ForgeAPI running in DEBUG mode — "
                "Telescope active at /_forge/telescope/requests. "
                "Do not use in production."
            )
            from .telescope import setup_telescope
            setup_telescope(self._app)

        if self._cfg.project.name:
            self._app.title = self._cfg.project.name
        if self._cfg.project.description:
            self._app.description = self._cfg.project.description

        if middleware:
            for item in middleware:
                if isinstance(item, tuple):
                    cls, kwargs = item
                    self._app.add_middleware(cls, **kwargs)
                else:
                    self._app.add_middleware(item)

        if logging:
            self._app.add_middleware(LoggingMiddleware)
            logger.debug("Middleware: access logging enabled")
        if request_id:
            self._app.add_middleware(RequestIDMiddleware)
            logger.debug("Middleware: request ID injection enabled")
        if cors is not False:
            origins = cors if isinstance(cors, list) else ["*"]
            add_cors(self._app, origins=origins)
            logger.debug("Middleware: CORS enabled, origins=%s", origins)
        if rate_limit is not False:
            rpm = rate_limit if not isinstance(rate_limit, bool) else 60
            self._app.add_middleware(RateLimitMiddleware, requests_per_minute=rpm)
            logger.debug("Middleware: rate limit %d req/min", rpm)
        if pagination is not False:
            default_limit = pagination if not isinstance(pagination, bool) else 0
            Paginator.configure(
                default_limit=default_limit or self._cfg.pagination.default_limit,
                max_limit=self._cfg.pagination.max_limit,
            )
            logger.debug("Pagination configured: default=%d max=%d", Paginator.DEFAULT_LIMIT, Paginator.MAX_LIMIT)
        if auth is not False:
            try:
                from .auth.backend import AuthBackend, set_global_backend
            except ImportError:
                raise ForgeAPIImportError(
                    "Auth backend could not be loaded.",
                    hint="Install the auth extra: pip install forge-kits[auth]",
                )
            strategy_name = auth if isinstance(auth, str) else ""
            self._auth = AuthBackend(strategy=self._build_strategy(strategy_name))
            set_global_backend(self._auth)
            logger.debug("Auth: strategy='%s' configured", strategy_name or self._cfg.auth.strategy)
        if events:
            from .events.bus import EventBus
            EventBus.get_instance().load_from_dir(self._cfg.structure.listeners_dir)
            logger.debug("Events: listeners loaded from '%s'", self._cfg.structure.listeners_dir)
        if permissions is True:
            permissions = self._find_permissions_model()
        if permissions not in (None, False):
            from .permissions.registry import setup_permissions
            setup_permissions(user_model=permissions)
            logger.debug("Permissions: enabled for model '%s'", getattr(permissions, "__name__", permissions))
        if controllers:
            self._load_controllers()
            logger.debug("Controllers: auto-discovered from '%s'", self._cfg.structure.controllers_dir)

    # ── Strategy builders ─────────────────────────────────────────────────────

    def _build_strategy(self, strategy: str = "", **kwargs):
        from .auth.strategies.jwt import JWTStrategy
        from .auth.strategies.cookie import CookieStrategy
        from .auth.strategies.telegram import TelegramStrategy

        resolved = strategy or self._cfg.auth.strategy
        builders = {
            "jwt":      lambda **kw: self._build_jwt(JWTStrategy, **kw),
            "cookie":   lambda **kw: self._build_cookie(CookieStrategy, **kw),
            "telegram": lambda **kw: self._build_telegram(TelegramStrategy, **kw),
        }
        builder = builders.get(resolved)
        if not builder:
            raise ForgeAPIConfigError(
                f"Unknown auth strategy '{resolved}'.",
                hint="Valid values: jwt, cookie, telegram. Check forgeapi.toml [auth] strategy.",
            )
        return builder(**kwargs)

    def _build_jwt(self, cls, **kwargs):
        cfg = self._cfg.auth
        return cls(
            secret_key=kwargs.pop("secret_key", os.getenv(cfg.jwt_secret_env, "")),
            access_token_expire_minutes=kwargs.pop("access_token_expire_minutes", cfg.access_ttl_minutes),
            refresh_token_expire_days=kwargs.pop("refresh_token_expire_days", cfg.refresh_ttl_days),
            **kwargs,
        )

    def _build_cookie(self, cls, **kwargs):
        cfg = self._cfg.auth
        return cls(
            cookie_name=kwargs.pop("cookie_name", cfg.cookie_name),
            httponly=kwargs.pop("httponly", cfg.cookie_httponly),
            secure=kwargs.pop("secure", cfg.cookie_secure),
            **kwargs,
        )

    def _build_telegram(self, cls, **kwargs):
        if "bot_token" not in kwargs:
            raw = os.getenv("BOT_TOKEN", "")
            tokens = [t.strip() for t in raw.split(",") if t.strip()]
            kwargs["bot_token"] = tokens or [""]
        kwargs.setdefault("debug", self._debug)
        return cls(**kwargs)

    # ── Permissions auto-discovery ────────────────────────────────────────────

    def _find_permissions_model(self) -> type:
        """Scan models_dir for the first class that inherits PermissionsMixin."""
        import importlib
        import sys
        from pathlib import Path
        from .permissions.mixins import PermissionsMixin

        directory = Path(self._cfg.structure.models_dir)
        if not directory.exists():
            raise ForgeAPIConfigError(
                f"models_dir '{directory}' does not exist.",
                hint=(
                    "Create the directory or update models_dir in forgeapi.toml. "
                    "Alternatively pass the model explicitly: Core(app, permissions=User)."
                ),
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
            raise ForgeAPIConfigError(
                f"No model with PermissionsMixin found in '{directory}'.",
                hint=(
                    "Add PermissionsMixin to your User model, "
                    "or pass it explicitly: Core(app, permissions=User)."
                ),
            )
        if len(found) > 1:
            names = ", ".join(c.__name__ for c in found)
            raise ForgeAPIConfigError(
                f"Multiple PermissionsMixin models found: {names}.",
                hint=f"Pass the model explicitly: Core(app, permissions=User).",
            )

        logger.debug("Permissions: auto-detected model '%s'", found[0].__name__)
        return found[0]

    # ── Controllers ───────────────────────────────────────────────────────────

    def _load_controllers(self, controllers_dir: str = "") -> None:
        import importlib
        import sys
        from pathlib import Path

        directory = Path(controllers_dir or self._cfg.structure.controllers_dir)
        if not directory.exists():
            return

        cwd = str(Path.cwd())
        if cwd not in sys.path:
            sys.path.insert(0, cwd)

        from .controllers.base import Controller as BaseController

        base = self._cfg.structure.base_prefix
        for f in sorted(directory.glob("**/*_controller.py")):
            try:
                rel = f.relative_to(Path.cwd())
            except ValueError:
                rel = f
            module_path = rel.with_suffix("").as_posix().replace("/", ".")
            mod = importlib.import_module(module_path)

            # New style: Controller subclasses with @route decorators
            ctrl_classes = [
                obj for _, obj in vars(mod).items()
                if isinstance(obj, type)
                and issubclass(obj, BaseController)
                and obj is not BaseController
                and obj.__module__ == mod.__name__
            ]
            if ctrl_classes:
                for cls in ctrl_classes:
                    if not cls._registered:
                        cls()
                    self._app.include_router(cls.router, prefix=base)
                continue

            # Legacy style: module-level router
            router = getattr(mod, "router", None)
            if router is None:
                continue
            if not router.routes:
                for attr_name, obj in vars(mod).items():
                    if (
                        isinstance(obj, type)
                        and attr_name.endswith("Controller")
                        and obj.__module__ == mod.__name__
                    ):
                        obj()
            self._app.include_router(router, prefix=base)

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
        """The configured AuthBackend, or ``None`` if auth was not enabled."""
        return self._auth

    @property
    def config(self) -> KitConfig:
        """Loaded :class:`~forgeapi.config.KitConfig`."""
        return self._cfg
