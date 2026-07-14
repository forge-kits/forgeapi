from __future__ import annotations

from typing import Annotated, Optional
from fastapi import Depends, Request

from .models import AuthUser


# ---------------------------------------------------------------------------
# These resolve through the default guard of the global ``auth`` facade.
# They are the recommended shorthand for single-guard applications.
#
# For multi-guard apps, use guard("name").current_user() instead:
#
#     from forgeapi.auth import guard
#     CurrentAdmin = guard("admin").current_user()
# ---------------------------------------------------------------------------


async def _resolve_current(request: Request) -> AuthUser:
    from .facade import auth
    return await auth._get(None)._authenticate(request, required=True)


async def _resolve_optional(request: Request) -> Optional[AuthUser]:
    from .facade import auth
    try:
        return await auth._get(None)._authenticate(request, required=False)
    except Exception:
        return None


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

Returns ``None`` instead of raising 401::

    from forgeapi.auth import OptionalUser

    @route.get("/feed")
    async def feed(self, user: OptionalUser):
        if user:
            return await personalised_feed(user.id)
        return await public_feed()
"""
