from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta
from typing import Optional

from fastapi import Request
from tortoise import timezone

from forgeapi.exceptions import ForgeAPIConfigError

from .models import AuthSession

#: ``last_activity`` is written at most this often (seconds), not on every request
TOUCH_INTERVAL = 60
#: one login in this many also deletes the expired sessions of everybody
PRUNE_ODDS = 50


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class SessionStore:
    """The ``auth_sessions`` table of the default Tortoise connection."""

    @staticmethod
    def _ready() -> None:
        if AuthSession._meta.default_connection is None:
            raise ForgeAPIConfigError(
                "The cookie strategy needs the auth_sessions table.",
                hint='Add "forgeapi.auth.models" to the models list in config/database.py and create the table.',
            )

    async def create(self, *, user_id: str, guard: str, lifetime: int, request: Request) -> str:
        """Start a session and return its token (the cookie value)."""
        self._ready()
        token = secrets.token_urlsafe(32)
        now = timezone.now()
        await AuthSession.create(
            id=_hash(token),
            user_id=str(user_id),
            guard=guard,
            ip_address=request.client.host if request.client else None,
            user_agent=(request.headers.get("user-agent") or "")[:255] or None,
            last_activity=now,
            expires_at=now + timedelta(seconds=lifetime),
        )
        if secrets.randbelow(PRUNE_ODDS) == 0:
            await self.prune()
        return token

    async def find(self, token: str, guard: str) -> Optional[AuthSession]:
        self._ready()
        return await AuthSession.get_or_none(id=_hash(token), guard=guard)

    async def touch(self, session: AuthSession, lifetime: int) -> None:
        """Slide the idle expiry forward, at most once per :data:`TOUCH_INTERVAL`."""
        now = timezone.now()
        if (now - session.last_activity).total_seconds() < TOUCH_INTERVAL:
            return
        await AuthSession.filter(id=session.id).update(
            last_activity=now,
            expires_at=now + timedelta(seconds=lifetime),
        )

    async def destroy(self, token: str, guard: str) -> None:
        self._ready()
        await AuthSession.filter(id=_hash(token), guard=guard).delete()

    async def destroy_for_user(self, user_id: str, guard: str, *, keep_token: Optional[str] = None) -> int:
        """Delete every session of the user, except the one of ``keep_token``. Returns how many."""
        self._ready()
        query = AuthSession.filter(user_id=str(user_id), guard=guard)
        if keep_token:
            query = query.exclude(id=_hash(keep_token))
        return await query.delete()

    async def prune(self) -> int:
        """Delete every expired session. Returns how many were removed."""
        self._ready()
        return await AuthSession.filter(expires_at__lte=timezone.now()).delete()
