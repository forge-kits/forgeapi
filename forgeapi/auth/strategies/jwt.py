import os
from datetime import datetime, timedelta, timezone
from typing import Optional

try:
    import jwt
except ImportError:
    from forgeapi.exceptions import ForgeAPIImportError
    raise ForgeAPIImportError(
        "JWTStrategy requires PyJWT.",
        hint="pip install forge-kits[auth]",
    )

from fastapi import HTTPException, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from .base import AuthStrategy
from ..models import AuthUser
from forgeapi.exceptions import ForgeAPIConfigError, TokenExpiredError, TokenInvalidError
from forgeapi.logging import log

_log = log.channel("auth.jwt")

ALLOWED_ALGORITHMS: frozenset = frozenset({"HS256", "HS384", "HS512"})


class JWTStrategy(AuthStrategy):
    """JWT authentication strategy using Bearer tokens.

    Reads the token from the ``Authorization: Bearer <token>`` header.
    Issues access tokens (short-lived) and refresh tokens (long-lived).

    Args:
        secret_key: HMAC secret used to sign tokens.  Falls back to the
            ``JWT_SECRET`` environment variable if omitted.
        algorithm: JWT signing algorithm.  Must be one of ``HS256``, ``HS384``,
            or ``HS512``.  Defaults to ``"HS256"``.
        access_token_expire_minutes: Lifetime of access tokens in minutes.
            Defaults to ``30``.
        refresh_token_expire_days: Lifetime of refresh tokens in days.
            Defaults to ``7``.

    Raises:
        ValueError: If neither ``secret_key`` nor ``JWT_SECRET`` env var is set.
        ForgeAPIConfigError: If ``algorithm`` is not in the allowed set.

    Example::

        strategy = JWTStrategy(secret_key="s3cr3t", access_token_expire_minutes=15)

        # issue tokens
        access = strategy.create_access_token({"sub": "user_42", "username": "alice"})
        refresh = strategy.create_refresh_token({"sub": "user_42"})

        # verify
        payload = strategy.decode(access)   # {"sub": "user_42", "username": "alice", ...}
    """

    _RESERVED_CLAIMS: frozenset = frozenset({"sub", "username", "exp", "iat", "type"})

    def __init__(
        self,
        secret_key: Optional[str] = None,
        algorithm: str = "HS256",
        access_token_expire_minutes: int = 30,
        refresh_token_expire_days: int = 7,
    ) -> None:
        self._secret = secret_key or os.getenv("JWT_SECRET", "")
        if not self._secret:
            raise ForgeAPIConfigError(
                "JWT secret key is not set.",
                hint="Pass secret_key= to JWTStrategy or set the JWT_SECRET environment variable.",
            )
        if algorithm not in ALLOWED_ALGORITHMS:
            raise ForgeAPIConfigError(
                f"JWT algorithm '{algorithm}' is not allowed.",
                hint=f"Use one of: {', '.join(sorted(ALLOWED_ALGORITHMS))}.",
            )
        self._algorithm = algorithm
        self._access_ttl = access_token_expire_minutes
        self._refresh_ttl = refresh_token_expire_days
        _log.debug("JWTStrategy ready: algorithm=%s access_ttl=%dm refresh_ttl=%dd", algorithm, access_token_expire_minutes, refresh_token_expire_days)

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

    def decode(self, token: str, *, expected_type: Optional[str] = None) -> dict:
        """Decode and verify a JWT token.

        Args:
            token: Raw JWT string (without ``"Bearer "`` prefix).
            expected_type: When set, the ``"type"`` claim in the payload must
                match this value or :class:`~forgeapi.exceptions.TokenInvalidError`
                is raised.  Use ``"access"`` or ``"refresh"``.

        Returns:
            Decoded claims dict.

        Raises:
            :class:`~forgeapi.exceptions.TokenExpiredError`: If the token is expired.
            :class:`~forgeapi.exceptions.TokenInvalidError`: If the token signature
                is invalid or ``expected_type`` does not match the ``"type"`` claim.

        Example::

            payload = strategy.decode(token, expected_type="access")
            user_id = payload["sub"]
        """
        try:
            payload = jwt.decode(token, self._secret, algorithms=[self._algorithm])
        except jwt.ExpiredSignatureError:
            _log.debug("JWT decode failed: token expired")
            raise TokenExpiredError("Token has expired")
        except jwt.InvalidTokenError:
            _log.warning("JWT decode failed: invalid token signature or structure")
            raise TokenInvalidError("Invalid token")

        if expected_type is not None and payload.get("type") != expected_type:
            _log.warning(
                "JWT decode failed: token type='%s', expected '%s'",
                payload.get("type"),
                expected_type,
            )
            raise TokenInvalidError(f"Invalid token type: expected '{expected_type}'")

        return payload

    def blacklist(self, token: str) -> None:
        """Mark a token as revoked.

        The default implementation is a no-op.  Override or replace with a
        Redis-backed implementation to enable actual revocation.

        Args:
            token: Raw JWT string to revoke.
        """
        _log.warning(
            "JWTStrategy.blacklist() called but token blacklisting is not implemented — "
            "the token will remain valid until expiry. "
            "Override this method or use a Redis-backed implementation."
        )

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
            _log.debug("JWT auth: no Bearer token in request")
            return None

        try:
            payload = self.decode(credentials.credentials, expected_type="access")
        except TokenExpiredError:
            raise HTTPException(status_code=401, detail="Token has expired")
        except TokenInvalidError as exc:
            raise HTTPException(status_code=401, detail=str(exc))

        _log.debug("JWT auth OK: user_id=%s", payload.get("sub"))
        return AuthUser(
            id=payload.get("sub"),
            username=payload.get("username"),
            extra={k: v for k, v in payload.items() if k not in self._RESERVED_CLAIMS},
            auth_method="jwt",
        )

    _bearer = HTTPBearer(auto_error=False)
