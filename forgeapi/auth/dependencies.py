from __future__ import annotations

from typing import Annotated, Optional
from fastapi import Depends, Request

from .models import AuthUser


# ---------------------------------------------------------------------------
# Shorthand dependencies for single-guard applications.  Pure proxies to the
# default guard of the global ``auth`` facade — no logic of their own, so
# behaviour is always identical to guard("...").current_user().
#
# For multi-guard apps, use guard("name").current_user() instead:
#
#     from forgeapi.auth import guard
#     CurrentAdmin = guard("admin").current_user()
# ---------------------------------------------------------------------------


async def _resolve_current(request: Request) -> AuthUser:
    from .facade import auth
    return await auth.guard().authenticate(request, required=True)


async def _resolve_optional(request: Request) -> Optional[AuthUser]:
    from .facade import auth
    return await auth.guard().authenticate(request, required=False)


CurrentUser = Annotated[AuthUser, Depends(_resolve_current)]
"""Required authenticated user from the default guard.

Raises HTTP 401 when credentials are absent or invalid::

    from forgeapi.auth import CurrentUser

    @route.get("/me")
    async def me(self, user: CurrentUser):
        return user

For a specific guard or a DB model result, use :func:`~forgeapi.auth.guard`::

    CurrentUser = guard("api").current_user()
"""

OptionalUser = Annotated[Optional[AuthUser], Depends(_resolve_optional)]
"""Optional authenticated user from the default guard.

Returns ``None`` when credentials are absent.  Present-but-invalid
credentials (expired token, bad signature) still raise 401 — a client
sending broken credentials is a client bug, not an anonymous visitor::

    from forgeapi.auth import OptionalUser

    @route.get("/feed")
    async def feed(self, user: OptionalUser):
        if user:
            return await personalised_feed(user.id)
        return await public_feed()
"""
