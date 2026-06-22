import base64
import hashlib
import hmac
import json
import os
from typing import Optional

from fastapi import Request, Response

from .base import AuthStrategy
from ..models import AuthUser


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

    def __init__(
        self,
        secret_key: Optional[str] = None,
        cookie_name: str = "session",
        max_age: int = 3600,
        httponly: bool = True,
        secure: bool = False,
        samesite: str = "lax",
    ) -> None:
        self._secret = secret_key or os.getenv("COOKIE_SECRET", "")
        if not self._secret:
            raise ValueError("Cookie secret key required. Pass secret_key= or set COOKIE_SECRET env var.")
        self._cookie_name = cookie_name
        self._max_age = max_age
        self._httponly = httponly
        self._secure = secure
        self._samesite = samesite

    def create_session(self, data: dict) -> str:
        """Encode and sign session data for use as a cookie value.

        Args:
            data: Any JSON-serialisable dict.  Include ``"sub"`` (user id) and
                ``"username"`` — those will be mapped to
                :class:`~forgeapi.auth.models.AuthUser` fields on read.

        Returns:
            Signed cookie string in the form ``<b64payload>.<signature>``.

        Example::

            value = strategy.create_session({"sub": "42", "username": "alice"})
            response.set_cookie("session", value)
        """
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
        response.delete_cookie(self._cookie_name)

    async def authenticate(self, request: Request) -> Optional[AuthUser]:
        """Read and verify the session cookie from the request.

        Args:
            request: Incoming FastAPI/Starlette request.

        Returns:
            :class:`~forgeapi.auth.models.AuthUser` on success, ``None``
            if the cookie is absent.

        Raises:
            :class:`fastapi.HTTPException` 401: If the cookie is present but
                the signature does not match or the payload is malformed.
        """
        raw = request.cookies.get(self._cookie_name)
        if not raw:
            return None

        data = self._verify(raw)
        return AuthUser(
            id=data.get("sub"),
            username=data.get("username"),
            extra={k: v for k, v in data.items() if k not in ("sub", "username")},
            auth_method="cookie",
        )

    def _sign(self, value: str) -> str:
        raw = hmac.new(self._secret.encode(), value.encode(), hashlib.sha256).digest()
        return base64.urlsafe_b64encode(raw).decode().rstrip("=")

    def _verify(self, cookie_value: str) -> dict:
        from fastapi import HTTPException
        try:
            payload, sig = cookie_value.rsplit(".", 1)
        except ValueError:
            raise HTTPException(status_code=401, detail="Malformed session cookie")

        if not hmac.compare_digest(self._sign(payload), sig):
            raise HTTPException(status_code=401, detail="Session cookie signature mismatch")

        try:
            return json.loads(base64.urlsafe_b64decode(payload + "==").decode())
        except Exception:
            raise HTTPException(status_code=401, detail="Invalid session cookie payload")
