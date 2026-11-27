from typing import Optional, Union

from fastapi import Request
from tortoise import timezone

from forgeapi.exceptions import ForgeAPIConfigError, SessionExpiredError, SessionInvalidError
from forgeapi.logging import log

from ..contracts import SessionCookie
from ..sessions import SessionStore
from .base import AuthStrategy

_log = log.channel("auth.cookie")


class CookieStrategy(AuthStrategy):
    """Login sessions kept in a table of the project, identified by a cookie.

    The cookie holds only a random token.  A logout deletes the session, so a
    copied cookie stops working at once.  The table is the ``Session`` model that
    ``forgeapi init`` puts in ``database/models/session.py``.

    Log in and out with the facade, it sets the cookie itself::

        await auth.login(user)
        await auth.logout()

    Args:
        session_model: The model whose table holds the sessions (see
            :class:`~forgeapi.auth.sessions.SessionStore` for its fields).
        cookie_name: Name of the session cookie.  Defaults to ``"session"``.
        lifetime: Seconds of inactivity after which the session expires.  Every
            request moves the expiry forward.  Defaults to ``3600``.
        absolute_lifetime: Seconds after which the session ends however active
            it is.  Defaults to ``None`` (no limit).
        httponly: Set the ``HttpOnly`` flag.  Defaults to ``True``.
        secure: Set the ``Secure`` flag (HTTPS only).  Defaults to ``True``.
        samesite: ``SameSite`` policy: ``"lax"``, ``"strict"``, or ``"none"``.
            Defaults to ``"lax"``.
    """

    challenge = None  # cookie sessions have no standard WWW-Authenticate scheme

    @classmethod
    def from_config(cls, cfg: dict) -> "CookieStrategy":
        """Build from a guard config dict.

        Recognised keys: ``session_model`` (required, dotted path), ``cookie_name``, ``lifetime`` (seconds),
        ``absolute_lifetime`` (seconds), ``httponly``, ``secure``, ``samesite``.
        """
        model = cfg.get("session_model")
        if model is None:
            raise ForgeAPIConfigError(
                "The cookie guard has no session_model.",
                hint='add "session_model": "database.models.session.Session" to the guard in config/auth.py',
            )
        if isinstance(model, str):
            from forgeapi.foundation import import_string

            model = import_string(model)
        return cls(
            model,
            cookie_name=cfg.get("cookie_name", "session"),
            lifetime=cfg.get("lifetime", 3600),
            absolute_lifetime=cfg.get("absolute_lifetime"),
            httponly=cfg.get("httponly", True),
            secure=cfg.get("secure", True),
            samesite=cfg.get("samesite", "lax"),
        )

    def __init__(
        self,
        session_model: type,
        cookie_name: str = "session",
        lifetime: int = 3600,
        absolute_lifetime: Optional[int] = None,
        httponly: bool = True,
        secure: bool = True,
        samesite: str = "lax",
    ) -> None:
        self._cookie_name = cookie_name
        self._lifetime = lifetime
        self._absolute_lifetime = absolute_lifetime
        self._httponly = httponly
        self._secure = secure
        self._samesite = samesite
        self._guard = "default"
        self._store = SessionStore(session_model)
        if not secure:
            _log.warning(
                "CookieStrategy: secure=False — session cookies will be sent over plain HTTP. "
                "Set secure=True for any deployment accessible over the internet."
            )
        _log.debug("CookieStrategy ready: cookie='%s' httponly=%s secure=%s", cookie_name, httponly, secure)

    def bind(self, guard_name: str) -> None:
        # a session belongs to one guard, so a cookie of one guard never logs in to another
        self._guard = guard_name

    def _cookie(self, value: Optional[str]) -> SessionCookie:
        return SessionCookie(
            name=self._cookie_name,
            value=value,
            max_age=self._lifetime,
            httponly=self._httponly,
            secure=self._secure,
            samesite=self._samesite,
        )

    async def authenticate(self, request: Request) -> Optional[Union[str, int]]:
        """Look the session cookie up and return its user id.

        Returns:
            The user id on success, ``None`` if the cookie is absent.

        Raises:
            :class:`~forgeapi.exceptions.SessionExpiredError`: If the session expired.
            :class:`~forgeapi.exceptions.SessionInvalidError`: If no such session exists
                (never issued, or logged out).
        """
        token = request.cookies.get(self._cookie_name)
        if not token:
            _log.debug("Cookie auth: no '%s' cookie in request", self._cookie_name)
            return None

        session = await self._store.find(token, self._guard)
        if session is None:
            _log.warning("Cookie auth rejected: unknown session")
            raise SessionInvalidError("Session not found")
        if self._expired(session):
            await self._store.destroy(token, self._guard)
            _log.warning("Cookie auth rejected: session expired (user=%s)", session.user_id)
            raise SessionExpiredError("Session has expired")

        await self._store.touch(session, self._lifetime)
        _log.debug("Cookie auth OK: user_id=%s", session.user_id)
        return session.user_id

    def _expired(self, session) -> bool:
        now = timezone.now()
        if session.expires_at <= now:
            return True
        if self._absolute_lifetime is not None:
            return (now - session.created_at).total_seconds() >= self._absolute_lifetime
        return False

    async def login(self, request: Request, user_id) -> SessionCookie:
        """Start a session for the user and return the cookie that carries it.

        A session the request already has is ended first, so a token set before
        the login cannot be reused after it.
        """
        old = request.cookies.get(self._cookie_name)
        if old:
            await self._store.destroy(old, self._guard)
        token = await self._store.create(
            user_id=str(user_id), guard=self._guard, lifetime=self._lifetime, request=request,
        )
        return self._cookie(token)

    async def logout(self, request: Request) -> SessionCookie:
        """End the session of the request and return the cookie that removes it."""
        token = request.cookies.get(self._cookie_name)
        if token:
            await self._store.destroy(token, self._guard)
        return self._cookie(None)

    async def logout_others(self, request: Request, user_id) -> int:
        """End every session of the user except the one of this request.  Returns how many."""
        return await self._store.destroy_for_user(
            str(user_id), self._guard, keep_token=request.cookies.get(self._cookie_name),
        )
