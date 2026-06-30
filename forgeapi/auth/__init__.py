from .backend import AuthBackend, CurrentUser, OptionalUser, set_global_backend
from .models import AuthUser, TelegramUser
from .strategies import AuthStrategy, JWTStrategy, CookieStrategy, TelegramStrategy


class _AuthProxy:
    """Shortcut to the active auth strategy.

    Instead of ``_global_backend.strategy.create_access_token(...)`` use::

        from forgeapi.auth import auth

        token = auth.create_access_token({"sub": str(user.id)})
        auth.set_cookie(response, {"sub": str(user.id)})
        auth.delete_cookie(response)
    """

    def __getattr__(self, name: str):
        from .backend import _global_backend
        if _global_backend is None:
            from forgeapi.exceptions import ForgeAPIConfigError
            raise ForgeAPIConfigError(
                "Auth backend is not configured.",
                hint="Enable auth in Core: Core(app, auth=True).",
            )
        return getattr(_global_backend.strategy, name)


auth = _AuthProxy()


__all__ = [
    "AuthBackend",
    "CurrentUser",
    "OptionalUser",
    "set_global_backend",
    "AuthUser",
    "TelegramUser",
    "AuthStrategy",
    "JWTStrategy",
    "CookieStrategy",
    "TelegramStrategy",
    "auth",
]
