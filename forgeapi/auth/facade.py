from __future__ import annotations

from typing import TYPE_CHECKING
from forgeapi.logging import log

if TYPE_CHECKING:
    from .guard import Guard

_log = log.channel("auth.facade")


class Auth:
    """Laravel-style auth facade — single entry point for all auth operations.

    Maintains a registry of named :class:`~forgeapi.auth.guard.Guard` instances.
    Guards are registered automatically by ``Core`` or manually via :meth:`register`.

    Import the global singleton::

        from forgeapi.auth import auth

    Shortcuts (use the default guard)::

        token   = auth.token(user)
        refresh = auth.refresh_token(user)
        payload = auth.decode(token)

    Specific guard::

        token = auth.token(admin_user, guard="admin")

    Get a guard instance to build dependencies::

        CurrentUser  = auth.guard("api").current_user()
        CurrentAdmin = auth.guard("admin").current_user()
    """

    def __init__(self) -> None:
        self._guards: dict[str, Guard] = {}
        self._default: str = "api"

    # ------------------------------------------------------------------
    # Guard registry
    # ------------------------------------------------------------------

    def register(self, name: str, guard: Guard) -> None:
        """Register a guard under *name*.

        Called automatically by ``Core``. Call manually when not using ``Core``::

            from forgeapi.auth.guard import Guard
            from forgeapi.auth.strategies import JWTStrategy

            g = Guard("api", JWTStrategy(secret_key="s3cr3t"), user_model=User)
            auth.register("api", g)

        Args:
            name:  Unique guard name (e.g. ``"api"``, ``"admin"``).
            guard: Configured :class:`~forgeapi.auth.guard.Guard` instance.
        """
        self._guards[name] = guard
        _log.debug(
            "Auth: registered guard '%s' (strategy=%s, model=%s)",
            name,
            type(guard._strategy).__name__,
            guard._user_model.__name__ if guard._user_model else "AuthUser",
        )

    def set_default(self, name: str) -> None:
        """Set which guard :meth:`token`, :meth:`decode`, etc. use by default.

        Called automatically by ``Core``.

        Args:
            name: Guard name that must already be registered.
        """
        self._default = name

    def guard(self, name: str) -> Guard:
        """Return a guard by name.

        Raises:
            ForgeAPIConfigError: If *name* is not registered.

        Example::

            CurrentAdmin = auth.guard("admin").current_user()
            token = auth.guard("admin").token(admin_user)
        """
        from forgeapi.exceptions import ForgeAPIConfigError
        if name not in self._guards:
            known = ", ".join(self._guards) or "none"
            raise ForgeAPIConfigError(
                f"Auth guard '{name}' is not configured.",
                hint=(
                    f"Registered guards: {known}. "
                    "Add [auth.guards.{name}] to forgeapi.toml or call auth.register()."
                ),
            )
        return self._guards[name]

    # ------------------------------------------------------------------
    # Shortcuts — all delegate to the default (or named) guard
    # ------------------------------------------------------------------

    def token(self, user, *, guard: str | None = None) -> str:
        """Create an access token for *user*.

        Args:
            user:  DB model instance or :class:`~forgeapi.auth.models.AuthUser`.
            guard: Guard name override (uses default when omitted).

        Example::

            token = auth.token(user)
            token = auth.token(admin_user, guard="admin")
        """
        return self._get(guard).token(user)

    def refresh_token(self, user, *, guard: str | None = None) -> str:
        """Create a refresh token for *user* (JWT guards only).

        Example::

            refresh = auth.refresh_token(user)
        """
        return self._get(guard).refresh_token(user)

    def decode(self, token: str, *, guard: str | None = None, expected_type: str | None = None) -> dict:
        """Decode and verify a JWT token.

        Args:
            token:         Raw JWT string.
            guard:         Guard name override.
            expected_type: ``"access"`` or ``"refresh"`` — validates the ``type`` claim.

        Example::

            payload = auth.decode(token)
            payload = auth.decode(token, expected_type="refresh")
        """
        return self._get(guard).decode(token, expected_type=expected_type)

    def set_cookie(self, response, data: dict, *, guard: str | None = None) -> None:
        """Sign ``data`` and write a session cookie on *response* (Cookie strategy only).

        Args:
            response: FastAPI ``Response`` object.
            data:     Session payload — include ``"sub"`` (user id), optionally ``"username"``.
            guard:    Guard name override.

        Example::

            auth.set_cookie(response, {"sub": str(user.id), "username": user.username})
        """
        from .strategies.cookie import CookieStrategy
        g = self._get(guard)
        if not isinstance(g._strategy, CookieStrategy):
            raise NotImplementedError(
                f"set_cookie() requires CookieStrategy, got {type(g._strategy).__name__}."
            )
        g._strategy.set_cookie(response, data)

    def delete_cookie(self, response, *, guard: str | None = None) -> None:
        """Remove the session cookie from *response* (Cookie strategy only).

        Args:
            response: FastAPI ``Response`` object.
            guard:    Guard name override.

        Example::

            auth.delete_cookie(response)
        """
        from .strategies.cookie import CookieStrategy
        g = self._get(guard)
        if not isinstance(g._strategy, CookieStrategy):
            raise NotImplementedError(
                f"delete_cookie() requires CookieStrategy, got {type(g._strategy).__name__}."
            )
        g._strategy.delete_cookie(response)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _get(self, name: str | None) -> Guard:
        return self.guard(name) if name else self.guard(self._default)


# ---------------------------------------------------------------------------
# Global singleton — ``from forgeapi.auth import auth``
# ---------------------------------------------------------------------------
auth = Auth()
