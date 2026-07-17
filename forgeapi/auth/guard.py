from __future__ import annotations

from typing import Annotated, Any, Optional, TYPE_CHECKING
from fastapi import Depends, HTTPException, Request
from forgeapi.exceptions import ForgeAPIAuthError
from forgeapi.logging import log

from .contracts import RefreshCapable, SessionIssuer, TokenIssuer

if TYPE_CHECKING:
    from .strategies.base import AuthStrategy

_log = log.channel("auth.guard")


class Guard:
    """Named authentication context — strategy + optional DB model.

    Each guard has its own strategy (JWT, Cookie, Telegram, custom) and
    optionally resolves the authenticated token to a real DB model instance.

    The guard is the **only** layer that speaks HTTP: strategies raise
    :class:`~forgeapi.exceptions.ForgeAPIAuthError` subclasses, and
    :meth:`authenticate` translates them to 401 responses with a uniform
    shape.  Capabilities (tokens, sessions) are dispatched via the protocols
    in :mod:`forgeapi.auth.contracts`, so custom strategies that implement
    them work automatically.

    Configure in code::

        from forgeapi.auth import auth, Guard
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

    @property
    def strategy(self) -> AuthStrategy:
        """The strategy this guard authenticates with (read-only)."""
        return self._strategy

    @property
    def user_model(self) -> type | None:
        """The DB model authenticated users resolve to, or ``None``."""
        return self._user_model

    # ------------------------------------------------------------------
    # Authentication — the single domain-error → HTTP translation point
    # ------------------------------------------------------------------

    async def authenticate(self, request: Request, *, required: bool = True) -> Any:
        """Authenticate *request* and return the user.

        Semantics (uniform across all strategies):

        * credentials **absent** → ``None`` if ``required=False``, else 401;
        * credentials **present but invalid** (expired, bad signature,
          user gone from DB) → 401 always, even when ``required=False`` —
          a client sending broken credentials is a client bug and silently
          downgrading it to anonymous would mask it.
        """
        try:
            auth_user = await self._strategy.authenticate(request)
        except ForgeAPIAuthError as exc:
            _log.debug(
                "Guard '%s': 401 (%s) on %s %s",
                self.name, exc.code, request.method, request.url.path,
            )
            raise self._unauthorized(str(exc), code=exc.code)

        if auth_user is None:
            if not required:
                return None
            _log.debug(
                "Guard '%s': 401 — no credentials on %s %s",
                self.name, request.method, request.url.path,
            )
            raise self._unauthorized("Not authenticated", code="missing_credentials")

        if self._user_model is None:
            return auth_user

        db_user = await self._user_model.get_or_none(id=auth_user.id)
        if db_user is None:
            _log.debug(
                "Guard '%s': token valid but user id=%s not in DB",
                self.name, auth_user.id,
            )
            raise self._unauthorized("User not found.", code="user_not_found")

        _log.debug("Guard '%s': authenticated user id=%s", self.name, auth_user.id)
        return db_user

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

        Returns ``None`` when credentials are absent.  Present-but-invalid
        credentials still raise 401 (see :meth:`authenticate`).

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
    # Token / session helpers — dispatched via capability protocols
    # ------------------------------------------------------------------

    def token(self, user: Any) -> str:
        """Create an access token (or signed session value) for *user*.

        Works with any strategy implementing
        :class:`~forgeapi.auth.contracts.TokenIssuer` or
        :class:`~forgeapi.auth.contracts.SessionIssuer`.

        Example::

            token = guard("api").token(user)
        """
        payload = self._build_payload(user)
        if isinstance(self._strategy, TokenIssuer):
            return self._strategy.create_access_token(payload)
        if isinstance(self._strategy, SessionIssuer):
            return self._strategy.create_session(payload)
        raise NotImplementedError(
            f"token() is not supported for {type(self._strategy).__name__} — "
            "the strategy implements neither TokenIssuer nor SessionIssuer."
        )

    def refresh_token(self, user: Any) -> str:
        """Create a refresh token for *user* (``RefreshCapable`` strategies).

        Example::

            refresh = guard("api").refresh_token(user)
        """
        if not isinstance(self._strategy, RefreshCapable):
            raise NotImplementedError(
                f"refresh_token() is not supported for {type(self._strategy).__name__} — "
                "the strategy does not implement RefreshCapable."
            )
        return self._strategy.create_refresh_token(self._build_payload(user))

    def decode(self, token: str, *, expected_type: str | None = None) -> dict:
        """Decode and verify a token issued by this guard (``TokenIssuer`` strategies).

        Example::

            payload = guard("api").decode(token)
            payload = guard("api").decode(token, expected_type="refresh")
        """
        if not isinstance(self._strategy, TokenIssuer):
            raise NotImplementedError(
                f"decode() is not supported for {type(self._strategy).__name__} — "
                "the strategy does not implement TokenIssuer."
            )
        return self._strategy.decode(token, expected_type=expected_type)

    def set_cookie(self, response, data: dict) -> None:
        """Sign *data* and write a session cookie on *response* (``SessionIssuer`` strategies).

        Example::

            guard("web").set_cookie(response, {"sub": str(user.id)})
        """
        if not isinstance(self._strategy, SessionIssuer):
            raise NotImplementedError(
                f"set_cookie() is not supported for {type(self._strategy).__name__} — "
                "the strategy does not implement SessionIssuer."
            )
        self._strategy.set_cookie(response, data)

    def delete_cookie(self, response) -> None:
        """Remove the session cookie from *response* (``SessionIssuer`` strategies).

        Example::

            guard("web").delete_cookie(response)
        """
        if not isinstance(self._strategy, SessionIssuer):
            raise NotImplementedError(
                f"delete_cookie() is not supported for {type(self._strategy).__name__} — "
                "the strategy does not implement SessionIssuer."
            )
        self._strategy.delete_cookie(response)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _unauthorized(self, detail: str, *, code: str) -> HTTPException:
        headers = {}
        if self._strategy.challenge:
            headers["WWW-Authenticate"] = f'{self._strategy.challenge} error="{code}"'
        return HTTPException(status_code=401, detail=detail, headers=headers or None)

    def _build_dep(self, *, required: bool) -> Any:
        _guard = self

        async def _resolve(request: Request):
            return await _guard.authenticate(request, required=required)

        model = self._user_model
        if model is None:
            from .models import AuthUser
            model = AuthUser

        if required:
            return Annotated[model, Depends(_resolve)]
        return Annotated[Optional[model], Depends(_resolve)]

    def _build_payload(self, user: Any) -> dict:
        """Build token claims for *user*.

        A model can control its claims by defining ``auth_claims() -> dict``
        (``"sub"`` is filled from ``user.id`` when omitted)::

            class User(ModelMixin, Model):
                def auth_claims(self) -> dict:
                    return {"username": self.username, "role": self.role}

        Without the hook: ``sub`` from ``user.id`` plus the first present
        attribute of ``username`` / ``email`` / ``name``.
        """
        from .models import AuthUser

        claims_hook = getattr(user, "auth_claims", None)
        if callable(claims_hook):
            payload = dict(claims_hook())
            payload.setdefault("sub", str(getattr(user, "id", "")))
            return payload

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
