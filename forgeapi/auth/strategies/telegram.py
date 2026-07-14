import hashlib
import hmac
import json
import time
from typing import List, Optional, Union
from urllib.parse import parse_qsl, unquote

from fastapi import Request

from forgeapi.logging import log
from .base import AuthStrategy
from ..models import AuthUser, TelegramUser

_log = log.channel("auth.telegram")


class TelegramStrategy(AuthStrategy):
    """Telegram WebApp ``initData`` authentication strategy.

    Validates the HMAC-SHA256 signature of the ``initData`` string that
    Telegram injects into every Mini App.  Accepts the data from two sources:

    * ``X-Telegram-Init-Data`` request header (preferred)
    * ``Authorization: tma <init_data>`` header

    Args:
        bot_token: Your Telegram bot token (``123456:ABC-...``).  Used to
            derive the HMAC secret key per the Telegram specification.
        max_age_seconds: Maximum age of the ``auth_date`` timestamp before the
            data is considered expired.  Defaults to ``86400`` (24 hours).

    Raises:
        :class:`fastapi.HTTPException` 401: If the signature is invalid, the
            ``hash`` field is missing, or the data has expired.

    Example::

        strategy = TelegramStrategy(bot_token="123:ABC", max_age_seconds=3600)

        # manual validation (e.g. in a webhook handler)
        tg_user = strategy.validate_init_data(raw_init_data_string)
        print(tg_user.id, tg_user.username)

    FastAPI usage::

        auth = AuthBackend(strategy=TelegramStrategy(bot_token="123:ABC"))
        CurrentUser = auth.current_user()

        @app.get("/me")
        async def me(user: CurrentUser):
            return {"tg_id": user.id, "username": user.username}
    """

    def __init__(self, bot_token: Union[str, List[str]], max_age_seconds: Optional[int] = 86400, debug: bool = False) -> None:
        tokens = [bot_token] if isinstance(bot_token, str) else list(bot_token)
        tokens = [t for t in tokens if t]
        if not tokens:
            _log.warning(
                "TelegramStrategy initialized with no bot tokens — "
                "all requests will be rejected. Set BOT_TOKEN in env."
            )
        self._secret_keys = [
            hmac.new(b"WebAppData", t.encode(), hashlib.sha256).digest()
            for t in tokens
        ]
        self._token_count = len(tokens)
        self._max_age = max_age_seconds
        self._debug = debug
        if debug:
            _log.warning("TelegramStrategy in DEBUG mode — auth_date expiry check disabled")
        _log.debug("TelegramStrategy ready with %d token(s), max_age=%s s, debug=%s", self._token_count, max_age_seconds, debug)

    def validate_init_data(self, init_data: str) -> TelegramUser:
        """Parse and validate raw Telegram ``initData``.

        Args:
            init_data: URL-encoded string from ``window.Telegram.WebApp.initData``.

        Returns:
            :class:`~forgeapi.auth.models.TelegramUser` with the validated
            user fields.

        Raises:
            :class:`fastapi.HTTPException` 401: On missing hash, expired data,
                or invalid signature.

        Example::

            raw = "query_id=AAH...&user=%7B%22id%22%3A123...%7D&auth_date=1700000000&hash=abc..."
            user = strategy.validate_init_data(raw)
            # TelegramUser(id=123, username="alice", ...)
        """
        from fastapi import HTTPException

        # parse_qsl handles URL-decoding of values internally; do NOT double-unquote
        # the outer string — it would cause + → space and %25 → % mismatches in
        # the signature check when field values contain encoded characters.
        params = dict(parse_qsl(init_data, keep_blank_values=True))

        received_hash = params.pop("hash", None)
        if not received_hash:
            _log.warning("Telegram auth rejected: missing 'hash' field in init data")
            raise HTTPException(status_code=401, detail="Missing hash in Telegram init data")

        try:
            auth_date = int(params.get("auth_date", 0))
        except ValueError:
            _log.warning("Telegram auth rejected: invalid auth_date value: %r", params.get("auth_date"))
            raise HTTPException(status_code=401, detail="Invalid auth_date in Telegram init data")
        age = time.time() - auth_date
        if self._debug:
            _log.debug("Telegram DEBUG: skipping auth_date expiry check (age=%.0f s)", age)
        elif self._max_age is not None and (age < 0 or age > self._max_age):
            _log.warning(
                "Telegram auth rejected: init data expired (age=%.0f s, max=%s s)",
                age, self._max_age,
            )
            raise HTTPException(status_code=401, detail="Telegram init data has expired")

        data_check = "\n".join(f"{k}={v}" for k, v in sorted(params.items()))
        results = [
            hmac.compare_digest(
                hmac.new(key, data_check.encode(), hashlib.sha256).hexdigest(),
                received_hash,
            )
            for key in self._secret_keys
        ]
        valid = any(results)
        if not valid:
            _log.warning(
                "Telegram auth rejected: HMAC signature mismatch (tried %d token(s))",
                self._token_count,
            )
            raise HTTPException(status_code=401, detail="Telegram init data signature is invalid")

        user_raw = params.get("user", "") or ""
        # The user field value may itself be URL-encoded JSON (e.g. when init_data
        # comes from a client that double-encodes it).  Try to decode once if needed.
        if user_raw.startswith("%"):
            user_raw = unquote(user_raw)
        try:
            user_data = json.loads(user_raw or "{}")
        except (json.JSONDecodeError, ValueError):
            _log.warning("Telegram auth rejected: malformed user JSON field: %r", user_raw[:200] if user_raw else user_raw)
            raise HTTPException(status_code=401, detail="Malformed user field in Telegram init data")

        tg_id = user_data.get("id", 0)
        if not tg_id:
            _log.warning("Telegram auth rejected: no user id in init data (bot update or missing user field)")
            raise HTTPException(status_code=401, detail="No user in Telegram init data")
        _log.debug("Telegram auth OK: user_id=%s username=%s", tg_id, user_data.get("username"))

        return TelegramUser(
            id=tg_id,
            username=user_data.get("username"),
            first_name=user_data.get("first_name"),
            last_name=user_data.get("last_name"),
            language_code=user_data.get("language_code"),
            auth_date=auth_date,
        )

    async def authenticate(self, request: Request) -> Optional[AuthUser]:
        """Validate Telegram init data from the request headers.

        Args:
            request: Incoming FastAPI/Starlette request.

        Returns:
            :class:`~forgeapi.auth.models.AuthUser` on success, ``None``
            if no Telegram header is present.
        """
        init_data = self._extract(request)
        if not init_data:
            _log.debug(
                "Telegram auth: no init data found in headers "
                "(expected X-Telegram-Init-Data or Authorization: tma ...)"
            )
            return None

        tg_user = self.validate_init_data(init_data)

        return AuthUser(
            id=tg_user.id,
            username=tg_user.username,
            extra={
                "first_name": tg_user.first_name,
                "last_name": tg_user.last_name,
                "language_code": tg_user.language_code,
                "auth_date": tg_user.auth_date,
            },
            auth_method="telegram",
        )

    @staticmethod
    def _extract(request: Request) -> Optional[str]:
        if header := request.headers.get("X-Telegram-Init-Data"):
            return header
        auth = request.headers.get("Authorization", "")
        if auth.lower().startswith("tma "):
            return auth[4:].strip()
        return None
