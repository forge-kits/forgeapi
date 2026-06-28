import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

try:
    import jwt
except ImportError:
    raise ImportError("JWTStrategy requires PyJWT. Install it: pip install forge-kits[auth]")

from fastapi import Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from .base import AuthStrategy
from ..models import AuthUser

logger = logging.getLogger("forgeapi.auth.jwt")


class JWTStrategy(AuthStrategy):
    """JWT authentication strategy using Bearer tokens.

    Reads the token from the ``Authorization: Bearer <token>`` header.
    Issues access tokens (short-lived) and refresh tokens (long-lived).

    Args:
        secret_key: HMAC secret used to sign tokens.  Falls back to the
            ``JWT_SECRET`` environment variable if omitted.
        algorithm: JWT signing algorithm.  Defaults to ``"HS256"``.
        access_token_expire_minutes: Lifetime of access tokens in minutes.
            Defaults to ``30``.
        refresh_token_expire_days: Lifetime of refresh tokens in days.
            Defaults to ``7``.

    Raises:
        ValueError: If neither ``secret_key`` nor ``JWT_SECRET`` env var is set.

    Example::

        strategy = JWTStrategy(secret_key="s3cr3t", access_token_expire_minutes=15)

        # issue tokens
        access = strategy.create_access_token({"sub": "user_42", "username": "alice"})
        refresh = strategy.create_refresh_token({"sub": "user_42"})

        # verify
        payload = strategy.decode(access)   # {"sub": "user_42", "username": "alice", ...}
    """

    _bearer = HTTPBearer(auto_error=False)

    def __init__(
        self,
        secret_key: Optional[str] = None,
        algorithm: str = "HS256",
        access_token_expire_minutes: int = 30,
        refresh_token_expire_days: int = 7,
    ) -> None:
        self._secret = secret_key or os.getenv("JWT_SECRET", "")
        if not self._secret:
            raise ValueError("JWT secret key required. Pass secret_key= or set JWT_SECRET env var.")
        self._algorithm = algorithm
        self._access_ttl = access_token_expire_minutes
        self._refresh_ttl = refresh_token_expire_days
        logger.debug("JWTStrategy ready: algorithm=%s access_ttl=%dm refresh_ttl=%dd", algorithm, access_token_expire_minutes, refresh_token_expire_days)

    def create_access_token(self, payload: dict) -> str:
        """Create a signed access token.

        Args:
            payload: Claims to embed.  Include ``"sub"`` (subject / user id)
                and any extra fields you need.  ``"exp"`` and ``"type"`` are
                added automatically — do not pass them.

        Returns:
            Signed JWT string.

        Example::

            token = strategy.create_access_token({"sub": "42", "role": "admin"})
        """
        expire = datetime.now(timezone.utc) + timedelta(minutes=self._access_ttl)
        return jwt.encode({**payload, "exp": expire, "type": "access"}, self._secret, algorithm=self._algorithm)

    def create_refresh_token(self, payload: dict) -> str:
        """Create a signed refresh token with a longer expiry.

        Args:
            payload: Same structure as ``create_access_token``.

        Returns:
            Signed JWT string with ``"type": "refresh"``.

        Example::

            refresh = strategy.create_refresh_token({"sub": "42"})
        """
        expire = datetime.now(timezone.utc) + timedelta(days=self._refresh_ttl)
        return jwt.encode({**payload, "exp": expire, "type": "refresh"}, self._secret, algorithm=self._algorithm)

    def decode(self, token: str) -> dict:
        """Decode and verify a JWT token.

        Args:
            token: Raw JWT string (without ``"Bearer "`` prefix).

        Returns:
            Decoded claims dict.

        Raises:
            :class:`fastapi.HTTPException` 401: If the token is expired or has
                an invalid signature.

        Example::

            payload = strategy.decode(token)
            user_id = payload["sub"]
        """
        try:
            return jwt.decode(token, self._secret, algorithms=[self._algorithm])
        except jwt.ExpiredSignatureError:
            from fastapi import HTTPException
            logger.debug("JWT decode failed: token expired")
            raise HTTPException(status_code=401, detail="Token has expired")
        except jwt.InvalidTokenError:
            from fastapi import HTTPException
            logger.debug("JWT decode failed: invalid token")
            raise HTTPException(status_code=401, detail="Invalid token")

    def blacklist(self, token: str) -> None:
        """Mark a token as revoked.

        The default implementation is a no-op.  Override or replace with a
        Redis-backed implementation to enable actual revocation.

        Args:
            token: Raw JWT string to revoke.
        """
        pass

    async def authenticate(self, request: Request) -> Optional[AuthUser]:
        """Extract and validate the Bearer token from the request.

        Args:
            request: Incoming FastAPI/Starlette request.

        Returns:
            :class:`~forgeapi.auth.models.AuthUser` if a valid Bearer token
            is present, ``None`` otherwise (no token in header).
        """
        credentials: Optional[HTTPAuthorizationCredentials] = await self._bearer(request)
        if not credentials:
            logger.debug("JWT auth: no Bearer token in request")
            return None

        payload = self.decode(credentials.credentials)
        reserved = {"sub", "username", "exp", "iat", "type"}
        logger.debug("JWT auth OK: user_id=%s", payload.get("sub"))

        return AuthUser(
            id=payload.get("sub"),
            username=payload.get("username"),
            extra={k: v for k, v in payload.items() if k not in reserved},
            auth_method="jwt",
        )
