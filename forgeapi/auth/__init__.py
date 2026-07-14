from .facade import auth, Auth
from .guard import Guard
from .dependencies import CurrentUser, OptionalUser
from .models import AuthUser, TelegramUser
from .strategies import AuthStrategy, JWTStrategy, CookieStrategy, TelegramStrategy


def guard(name: str) -> Guard:
    """Return a configured guard by name. Shorthand for ``auth.guard(name)``.

    Use to build per-guard dependencies in multi-guard apps::

        from forgeapi.auth import guard

        CurrentUser  = guard("api").current_user()    # → User from DB
        CurrentAdmin = guard("admin").current_user()  # → Admin from DB

    Args:
        name: Guard name from ``forgeapi.toml`` or :meth:`~Auth.register`.
    """
    return auth.guard(name)


__all__ = [
    "auth", "Auth",
    "guard", "Guard",
    "CurrentUser", "OptionalUser",
    "AuthUser", "TelegramUser",
    "AuthStrategy", "JWTStrategy", "CookieStrategy", "TelegramStrategy",
]
