from __future__ import annotations

from typing import Callable, TYPE_CHECKING
from forgeapi.logging import log

if TYPE_CHECKING:
    from .guard import Guard
    from .strategies.base import AuthStrategy

_log = log.channel("auth.facade")


class Auth:
    """Laravel-style auth facade — single entry point for all auth operations.

    Pure delegation layer: maintains a registry of named
    :class:`~forgeapi.auth.guard.Guard` instances and a registry of strategy
    factories.  All operations forward to a guard — the facade itself
    contains no auth logic.

    Import the global singleton::

        from forgeapi.auth import auth

    Shortcuts (use the default guard)::

        token = auth.token(user)

    Specific guard::

        token = auth.token(admin_user, guard="admin")

    Get a guard instance to build dependencies::

        CurrentUser  = auth.guard("api").current_user()
        CurrentAdmin = auth.guard("admin").current_user()

    Register a custom strategy (Laravel ``Auth::extend`` equivalent)::

        auth.extend("apikey", ApiKeyStrategy)
    """

    def __init__(self) -> None:
        self._guards: dict[str, Guard] = {}
        self._default: str = "api"
        self._factories: dict[str, Callable[[dict], "AuthStrategy"]] = {}

    # ------------------------------------------------------------------
    # Guard registry
    # ------------------------------------------------------------------

    def register(self, name: str, guard: Guard) -> None:
        """Register a guard under *name*.

        Called automatically by ``Core``. Call manually when not using ``Core``::

            from forgeapi.auth import auth, Guard
            from forgeapi.auth.strategies import CookieStrategy

            g = Guard("web", CookieStrategy(secret="s3cr3t"), user_model=User)
            auth.register("web", g)

        Args:
            name:  Unique guard name (e.g. ``"api"``, ``"admin"``).
            guard: Configured :class:`~forgeapi.auth.guard.Guard` instance.
        """
        self._guards[name] = guard
        _log.debug(
            "Auth: registered guard '%s' (strategy=%s, model=%s)",
            name,
            type(guard.strategy).__name__,
            guard.user_model.__name__ if guard.user_model else "AuthUser",
        )

    def set_default(self, name: str) -> None:
        """Set which guard :meth:`token`, etc. use by default.

        Called automatically by ``Core``.

        Args:
            name: Guard name that must already be registered.
        """
        self._default = name

    def guard(self, name: str | None = None) -> Guard:
        """Return a guard by name, or the default guard when *name* is omitted.

        Raises:
            ForgeAPIConfigError: If the guard is not registered.

        Example::

            CurrentAdmin = auth.guard("admin").current_user()
            token = auth.guard().token(user)   # default guard
        """
        from forgeapi.exceptions import ForgeAPIConfigError
        resolved = name or self._default
        if resolved not in self._guards:
            known = ", ".join(self._guards) or "none"
            raise ForgeAPIConfigError(
                f"Auth guard '{resolved}' is not configured.",
                hint=(
                    f"Registered guards: {known}. "
                    "Add the guard to your auth config or call auth.register()."
                ),
            )
        return self._guards[resolved]

    @property
    def is_configured(self) -> bool:
        """``True`` when at least one guard is registered."""
        return bool(self._guards)

    # ------------------------------------------------------------------
    # Strategy factories — Laravel ``Auth::extend`` equivalent
    # ------------------------------------------------------------------

    def extend(self, name: str, strategy_cls) -> None:
        """Register a custom strategy under *name*.

        *strategy_cls* must implement
        :meth:`~forgeapi.auth.strategies.base.AuthStrategy.from_config`
        (the default implementation maps config keys to constructor kwargs).

        Example::

            from forgeapi.auth import auth

            auth.extend("apikey", ApiKeyStrategy)
            # now "apikey" is a valid strategy name in the auth config
        """
        self._factories[name] = strategy_cls
        _log.debug("Auth: extended with strategy '%s' (%s)", name, strategy_cls.__name__)

    def create_strategy(self, name: str, cfg: dict | None = None) -> "AuthStrategy":
        """Instantiate a strategy by name from a config dict.

        Resolves built-in strategies (``cookie``, ``telegram``) and
        anything registered via :meth:`extend`.

        Example::

            strategy = auth.create_strategy("cookie", {"secret": "s3cr3t"})
        """
        factory = self._factories.get(name) or self._builtin_strategy(name)
        return factory.from_config(cfg or {})

    @staticmethod
    def _builtin_strategy(name: str):
        # imported lazily — strategies may require optional dependencies
        if name == "cookie":
            from .strategies.cookie import CookieStrategy
            return CookieStrategy
        if name == "telegram":
            from .strategies.telegram import TelegramStrategy
            return TelegramStrategy
        from forgeapi.exceptions import ForgeAPIConfigError
        raise ForgeAPIConfigError(
            f"Unknown auth strategy '{name}'.",
            hint=(
                "Valid values: cookie, telegram, or a custom strategy "
                "registered via auth.extend()."
            ),
        )

    # ------------------------------------------------------------------
    # Shortcuts — all delegate to the default (or named) guard
    # ------------------------------------------------------------------

    def token(self, user, *, guard: str | None = None) -> str:
        """Create a session token for *user*.

        Args:
            user:  DB model instance or :class:`~forgeapi.auth.models.AuthUser`.
            guard: Guard name override (uses default when omitted).

        Example::

            token = auth.token(user)
            token = auth.token(admin_user, guard="admin")
        """
        return self.guard(guard).token(user)

    def set_cookie(self, response, data: dict, *, guard: str | None = None) -> None:
        """Sign ``data`` and write a session cookie (``SessionIssuer`` strategies).

        Args:
            response: FastAPI ``Response`` object.
            data:     Session payload — include ``"sub"`` (user id), optionally ``"username"``.
            guard:    Guard name override.

        Example::

            auth.set_cookie(response, {"sub": str(user.id), "username": user.username})
        """
        self.guard(guard).set_cookie(response, data)

    def delete_cookie(self, response, *, guard: str | None = None) -> None:
        """Remove the session cookie (``SessionIssuer`` strategies).

        Args:
            response: FastAPI ``Response`` object.
            guard:    Guard name override.

        Example::

            auth.delete_cookie(response)
        """
        self.guard(guard).delete_cookie(response)


# ---------------------------------------------------------------------------
# Global singleton — ``from forgeapi.auth import auth``
# ---------------------------------------------------------------------------
auth = Auth()
