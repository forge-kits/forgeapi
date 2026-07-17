import base64
import binascii
import hashlib
import hmac
import json
import os
import time
from typing import Optional

from fastapi import Request, Response

from forgeapi.exceptions import SessionExpiredError, SessionInvalidError
from forgeapi.logging import log
from .base import AuthStrategy
from ..models import AuthUser

_log = log.channel("auth.cookie")


class CookieStrategy(AuthStrategy):
    """Session cookie authentication strategy.

    Stores a signed JSON payload in an HTTP cookie.  The signature is an
    HMAC-SHA256 digest computed from the base64-encoded payload, preventing
    tampering without requiring a database round-trip.

    Args:
        secret_key: HMAC signing secret.  Falls back to the ``COOKIE_SECRET``
            environment variable if omitted.
        cookie_name: Name of the session cookie.  Defaults to ``"session"``.
        max_age: Cookie lifetime in seconds.  Defaults to ``3600`` (1 hour).
        httponly: Set the ``HttpOnly`` flag.  Defaults to ``True``.
        secure: Set the ``Secure`` flag (HTTPS only).  Defaults to ``False``.
        samesite: ``SameSite`` policy: ``"lax"``, ``"strict"``, or ``"none"``.
            Defaults to ``"lax"``.

    Raises:
        ValueError: If neither ``secret_key`` nor ``COOKIE_SECRET`` is set.

    Example::

        strategy = CookieStrategy(secret_key="s3cr3t")

        # in a login endpoint
        @router.post("/login")
        async def login(response: Response):
            strategy.set_cookie(response, {"sub": "42", "username": "alice"})
            return {"ok": True}

        # in a logout endpoint
        @router.post("/logout")
        async def logout(response: Response):
            strategy.delete_cookie(response)
            return {"ok": True}
    """

    challenge = None  # cookie sessions have no standard WWW-Authenticate scheme

    @classmethod
    def from_config(cls, cfg: dict) -> "CookieStrategy":
        """Build from a guard config dict.

        Recognised keys: ``secret`` (raw value), ``secret_env`` (env var name,
        default ``COOKIE_SECRET``), ``cookie_name``, ``max_age`` (seconds),
        ``httponly``, ``secure``, ``samesite``.
        """
        from forgeapi.exceptions import ForgeAPIConfigError

        env_name = cfg.get("secret_env", "COOKIE_SECRET")
        secret = cfg.get("secret") or os.getenv(env_name, "")
        if not secret:
            raise ForgeAPIConfigError(
                "Cookie secret is not set.",
                hint=(
                    f"Set the {env_name} environment variable, "
                    "or add 'secret' to the guard config."
                ),
            )
        return cls(
            secret_key=secret,
            cookie_name=cfg.get("cookie_name", "session"),
            max_age=cfg.get("max_age", 3600),
            httponly=cfg.get("httponly", True),
            secure=cfg.get("secure", True),
            samesite=cfg.get("samesite", "lax"),
        )

    def __init__(
        self,
        secret_key: Optional[str] = None,
        cookie_name: str = "session",
        max_age: int = 3600,
        httponly: bool = True,
        secure: bool = True,
        samesite: str = "lax",
    ) -> None:
        self._secret = secret_key or os.getenv("COOKIE_SECRET", "")
        if not self._secret:
            from forgeapi.exceptions import ForgeAPIConfigError
            raise ForgeAPIConfigError(
                "Cookie secret key is not set.",
                hint="Pass secret_key= to CookieStrategy or set the COOKIE_SECRET environment variable.",
            )
        self._cookie_name = cookie_name
        self._max_age = max_age
        self._httponly = httponly
        self._secure = secure
        self._samesite = samesite
        if not secure:
            _log.warning(
                "CookieStrategy: secure=False — session cookies will be sent over plain HTTP. "
                "Set secure=True for any deployment accessible over the internet."
            )
        _log.debug("CookieStrategy ready: cookie='%s' httponly=%s secure=%s", cookie_name, httponly, secure)

    def create_session(self, data: dict) -> str:
        """Encode and sign session data for use as a cookie value.

        Args:
            data: Any JSON-serialisable dict.  Include ``"sub"`` (user id) and
                ``"username"`` — those will be mapped to
                :class:`~forgeapi.auth.models.AuthUser` fields on read.
                An ``"exp"`` (Unix timestamp) claim is added automatically.

        Returns:
            Signed cookie string in the form ``<b64payload>.<signature>``.

        Example::

            value = strategy.create_session({"sub": "42", "username": "alice"})
            response.set_cookie("session", value)
        """
        data = {**data, "exp": int(time.time()) + self._max_age}
        payload = base64.urlsafe_b64encode(json.dumps(data).encode()).decode()
        return f"{payload}.{self._sign(payload)}"

    def set_cookie(self, response: Response, data: dict) -> None:
        """Sign ``data`` and write it as a session cookie on the response.

        Args:
            response: FastAPI ``Response`` (or ``JSONResponse``) object.
            data: Session payload (see :meth:`create_session`).

        Example::

            @router.post("/login")
            async def login(payload: LoginPayload, response: Response):
                strategy.set_cookie(response, {"sub": user.id, "username": user.username})
                return {"ok": True}
        """
        response.set_cookie(
            key=self._cookie_name,
            value=self.create_session(data),
            max_age=self._max_age,
            path="/",
            httponly=self._httponly,
            secure=self._secure,
            samesite=self._samesite,
        )

    def delete_cookie(self, response: Response) -> None:
        """Remove the session cookie from the response.

        Args:
            response: FastAPI ``Response`` object.

        Example::

            @router.post("/logout")
            async def logout(response: Response):
                strategy.delete_cookie(response)
                return {"ok": True}
        """
        response.delete_cookie(
            self._cookie_name,
            path="/",
            httponly=self._httponly,
            secure=self._secure,
            samesite=self._samesite,
        )

    async def authenticate(self, request: Request) -> Optional[AuthUser]:
        """Read and verify the session cookie from the request.

        Args:
            request: Incoming FastAPI/Starlette request.

        Returns:
            :class:`~forgeapi.auth.models.AuthUser` on success, ``None``
            if the cookie is absent.

        Raises:
            :class:`~forgeapi.exceptions.SessionExpiredError`: If the session expired.
            :class:`~forgeapi.exceptions.SessionInvalidError`: If the cookie is
                malformed or its signature does not match.
        """
        raw = request.cookies.get(self._cookie_name)
        if not raw:
            _log.debug("Cookie auth: no '%s' cookie in request", self._cookie_name)
            return None

        data = self._verify(raw)
        if data.get("exp", 0) <= time.time():
            _log.warning("Cookie auth rejected: session expired (sub=%s)", data.get("sub"))
            raise SessionExpiredError("Session has expired")
        _log.debug("Cookie auth OK: user_id=%s", data.get("sub"))
        return AuthUser(
            id=data.get("sub"),
            username=data.get("username"),
            extra={k: v for k, v in data.items() if k not in ("sub", "username", "exp")},
            auth_method="cookie",
        )

    def _sign(self, value: str) -> str:
        raw = hmac.new(self._secret.encode(), value.encode(), hashlib.sha256).digest()
        return base64.urlsafe_b64encode(raw).decode().rstrip("=")

    def _verify(self, cookie_value: str) -> dict:
        try:
            payload, sig = cookie_value.rsplit(".", 1)
        except ValueError:
            _log.warning("Cookie auth rejected: malformed cookie value")
            raise SessionInvalidError("Malformed session cookie")

        if not hmac.compare_digest(self._sign(payload), sig):
            _log.warning("Cookie auth rejected: signature mismatch")
            raise SessionInvalidError("Session cookie signature mismatch")

        try:
            return json.loads(base64.urlsafe_b64decode(payload + "==").decode())
        except (json.JSONDecodeError, UnicodeDecodeError, binascii.Error) as exc:
            _log.warning("Cookie auth rejected: invalid session payload: %s", exc)
            raise SessionInvalidError("Invalid session")
