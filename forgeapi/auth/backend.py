import logging
from typing import Annotated, Optional
from fastapi import Depends, HTTPException, Request

from .models import AuthUser
from .strategies.base import AuthStrategy

logger = logging.getLogger("forgeapi.auth")

_global_backend: Optional["AuthBackend"] = None


def _get_global_backend() -> "AuthBackend":
    if _global_backend is None:
        raise RuntimeError(
            "Global auth backend not configured. "
            "Call Core(app, auth=True)() or forgeapi.auth.set_global_backend(auth) first."
        )
    return _global_backend


async def _global_current_user(request: Request) -> AuthUser:
    backend = _get_global_backend()
    return await backend._resolve_user(request, required=True)


async def _global_optional_user(request: Request) -> Optional[AuthUser]:
    if _global_backend is None:
        return None
    return await _global_backend._resolve_user(request, required=False)


# Module-level type aliases — usable in generated router templates
CurrentUser = Annotated[AuthUser, Depends(_global_current_user)]
"""Type alias for a **required** authenticated user dependency.

Import and use as a type annotation in your endpoints::

    from forgeapi.auth import CurrentUser

    @router.get("/me")
    async def me(user: CurrentUser):
        return {"id": user.id, "username": user.username}

Requires :func:`set_global_backend` or :meth:`Core(app, auth=True)` to have been
called before the first request.
"""

OptionalUser = Annotated[Optional[AuthUser], Depends(_global_optional_user)]
"""Type alias for an **optional** authenticated user dependency.

Returns ``None`` when no valid credentials are present instead of raising 401::

    from forgeapi.auth import OptionalUser

    @router.get("/feed")
    async def feed(user: OptionalUser):
        if user:
            return personalised_feed(user.id)
        return public_feed()
"""


def set_global_backend(backend: "AuthBackend") -> None:
    """Register *backend* as the global singleton used by :data:`CurrentUser`.

    Called automatically by :meth:`Core(app, auth=True)`.  Call it directly only
    when you manage the ``AuthBackend`` yourself without ``Kit``.

    Args:
        backend: Configured :class:`AuthBackend` instance.

    Example::

        auth = AuthBackend(strategy=JWTStrategy(secret_key="s3cr3t"))
        set_global_backend(auth)
    """
    global _global_backend
    _global_backend = backend
    logger.debug("Global auth backend set: strategy=%s", type(backend.strategy).__name__)


class AuthBackend:
    """Unified authentication interface.

    Wraps any :class:`~forgeapi.auth.strategies.base.AuthStrategy` and
    exposes a consistent API regardless of the underlying mechanism (JWT,
    cookie, Telegram).

    Args:
        strategy: Authentication strategy to use.

    Example — JWT::

        from forgeapi.auth import AuthBackend, JWTStrategy

        auth = AuthBackend(strategy=JWTStrategy(secret_key="s3cr3t"))
        CurrentUser = auth.current_user()

        @app.get("/me")
        async def me(user: CurrentUser):
            return user

    Example — Telegram::

        auth = AuthBackend(strategy=TelegramStrategy(bot_token="123:ABC"))
        CurrentUser = auth.current_user()

    Example — switching strategies at runtime::

        if settings.auth_method == "cookie":
            auth = AuthBackend(strategy=CookieStrategy(secret_key="s3cr3t"))
        else:
            auth = AuthBackend(strategy=JWTStrategy(secret_key="s3cr3t"))
    """

    def __init__(self, strategy: AuthStrategy) -> None:
        self._strategy = strategy

    def current_user(self) -> type:
        """Return an ``Annotated`` type that requires a valid authenticated user.

        Use the return value as a **type annotation** in endpoint function
        signatures — FastAPI resolves it as a dependency automatically.

        Returns:
            ``Annotated[AuthUser, Depends(...)]`` type alias.

        Example::

            auth = AuthBackend(strategy=JWTStrategy(secret_key="s3cr3t"))
            CurrentUser = auth.current_user()

            @app.get("/profile")
            async def profile(user: CurrentUser):
                return {"id": user.id}
        """
        strategy = self._strategy

        async def _get_user(request: Request) -> AuthUser:
            user = await strategy.authenticate(request)
            if not user:
                raise HTTPException(
                    status_code=401,
                    detail="Not authenticated",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            return user

        return Annotated[AuthUser, Depends(_get_user)]

    def optional_user(self) -> type:
        """Return an ``Annotated`` type for an optional authenticated user.

        Returns ``None`` instead of raising 401 when credentials are absent.

        Returns:
            ``Annotated[Optional[AuthUser], Depends(...)]`` type alias.

        Example::

            OptionalUser = auth.optional_user()

            @app.get("/content")
            async def content(user: OptionalUser):
                if user:
                    return premium_content(user.id)
                return free_content()
        """
        strategy = self._strategy

        async def _get_user(request: Request) -> Optional[AuthUser]:
            return await strategy.authenticate(request)

        return Annotated[Optional[AuthUser], Depends(_get_user)]

    async def _resolve_user(self, request: Request, required: bool) -> Optional[AuthUser]:
        user = await self._strategy.authenticate(request)
        if required and not user:
            logger.debug("Auth: unauthenticated request to %s %s", request.method, request.url.path)
            raise HTTPException(
                status_code=401,
                detail="Not authenticated",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return user

    @property
    def strategy(self) -> AuthStrategy:
        """The underlying :class:`~forgeapi.auth.strategies.base.AuthStrategy` instance."""
        return self._strategy
