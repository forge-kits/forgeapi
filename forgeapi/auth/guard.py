from __future__ import annotations

from typing import Annotated, Any, Optional, TYPE_CHECKING
from fastapi import Depends, HTTPException, Request
from forgeapi.logging import log

if TYPE_CHECKING:
    from .strategies.base import AuthStrategy

_log = log.channel("auth.guard")


class Guard:
    """Named authentication context — strategy + optional DB model.

    Each guard has its own strategy (JWT, Cookie, Telegram) and optionally
    resolves the authenticated token to a real DB model instance.

    Configure in ``forgeapi.toml``::

        [auth.guards.api]
        strategy = "jwt"
        model = "app.models.User"

        [auth.guards.admin]
        strategy = "jwt"
        model = "app.models.Admin"

    Or register in code::

        from forgeapi.auth import auth
        from forgeapi.auth.guard import Guard
        from forgeapi.auth.strategies import JWTStrategy

        api_guard = Guard("api", JWTStrategy(secret_key="..."), user_model=User)
        auth.register("api", api_guard)

    Usage in controllers::

        from forgeapi.auth import guard

        CurrentUser  = guard("api").current_user()
        CurrentAdmin = guard("admin").current_user()

        @route.get("/me")
        async def me(self, user: CurrentUser):
            return user  # ← real User from DB, not a DTO
    """

    def __init__(
        self,
        name: str,
        strategy: AuthStrategy,
        user_model: type | None = None,
    ) -> None:
        self.name = name
        self._strategy = strategy
        self._user_model = user_model
        # cached Annotated types — built once per guard instance
        self._current_dep: Any = None
        self._optional_dep: Any = None

    # ------------------------------------------------------------------
    # FastAPI dependencies
    # ------------------------------------------------------------------

    def current_user(self) -> Any:
        """Return an ``Annotated`` dependency — required authenticated user.

        Raises HTTP 401 if no valid credentials are present.
        Returns the configured DB model, or :class:`~forgeapi.auth.models.AuthUser`
        when no model is set.

        Example::

            CurrentUser = guard("api").current_user()

            @route.get("/profile")
            async def profile(self, user: CurrentUser):
                return user
        """
        if self._current_dep is None:
            self._current_dep = self._build_dep(required=True)
        return self._current_dep

    def optional_user(self) -> Any:
        """Return an ``Annotated`` dependency — optional authenticated user.

        Returns ``None`` instead of raising 401 when credentials are absent.

        Example::

            OptionalUser = guard("api").optional_user()

            @route.get("/feed")
            async def feed(self, user: OptionalUser):
                if user:
                    return await personalised_feed(user.id)
                return await public_feed()
        """
        if self._optional_dep is None:
            self._optional_dep = self._build_dep(required=False)
        return self._optional_dep

    # ------------------------------------------------------------------
    # Token helpers
    # ------------------------------------------------------------------

    def token(self, user: Any) -> str:
        """Create an access token for *user*.

        Works with JWT and Cookie strategies.
        Pass the DB model instance or :class:`~forgeapi.auth.models.AuthUser`.

        Example::

            token = guard("api").token(user)
        """
        from .strategies.jwt import JWTStrategy
        from .strategies.cookie import CookieStrategy

        payload = self._build_payload(user)

        if isinstance(self._strategy, JWTStrategy):
            return self._strategy.create_access_token(payload)
        if isinstance(self._strategy, CookieStrategy):
            return self._strategy.create_session(payload)

        raise NotImplementedError(
            f"token() is not supported for {type(self._strategy).__name__}."
        )

    def refresh_token(self, user: Any) -> str:
        """Create a refresh token for *user* (JWT only).

        Example::

            refresh = guard("api").refresh_token(user)
        """
        from .strategies.jwt import JWTStrategy
        if not isinstance(self._strategy, JWTStrategy):
            raise NotImplementedError(
                f"refresh_token() requires JWTStrategy, got {type(self._strategy).__name__}."
            )
        return self._strategy.create_refresh_token(self._build_payload(user))

    def decode(self, token: str, *, expected_type: str | None = None) -> dict:
        """Decode and verify a token issued by this guard (JWT only).

        Example::

            payload = guard("api").decode(token)
            payload = guard("api").decode(token, expected_type="refresh")
        """
        from .strategies.jwt import JWTStrategy
        if not isinstance(self._strategy, JWTStrategy):
            raise NotImplementedError(
                f"decode() requires JWTStrategy, got {type(self._strategy).__name__}."
            )
        return self._strategy.decode(token, expected_type=expected_type)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _build_dep(self, *, required: bool) -> Any:
        _guard = self

        async def _resolve(request: Request):
            return await _guard._authenticate(request, required=required)

        model = self._user_model
        if model is None:
            from .models import AuthUser
            model = AuthUser

        if required:
            return Annotated[model, Depends(_resolve)]
        return Annotated[Optional[model], Depends(_resolve)]

    async def _authenticate(self, request: Request, *, required: bool) -> Any:
        auth_user = await self._strategy.authenticate(request)

        if auth_user is None:
            if required:
                _log.debug(
                    "Guard '%s': 401 — no credentials on %s %s",
                    self.name, request.method, request.url.path,
                )
                raise HTTPException(
                    status_code=401,
                    detail="Not authenticated",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            return None

        if self._user_model is None:
            return auth_user

        db_user = await self._user_model.get_or_none(id=auth_user.id)
        if db_user is None:
            _log.debug(
                "Guard '%s': token valid but user id=%s not in DB",
                self.name, auth_user.id,
            )
            if required:
                raise HTTPException(status_code=401, detail="User not found.")
            return None

        _log.debug("Guard '%s': authenticated user id=%s", self.name, auth_user.id)
        return db_user

    def _build_payload(self, user: Any) -> dict:
        from .models import AuthUser
        if isinstance(user, AuthUser):
            payload: dict = {"sub": str(user.id)}
            if user.username:
                payload["username"] = user.username
            return payload

        payload = {"sub": str(getattr(user, "id", ""))}
        for field in ("username", "email", "name"):
            val = getattr(user, field, None)
            if val is not None:
                payload[field] = str(val)
                break
        return payload
