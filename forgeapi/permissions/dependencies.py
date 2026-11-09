from __future__ import annotations

from fastapi import Depends, HTTPException, Request
from tortoise.models import Model

async def _resolve_db_user(request: Request, guard_name: str | None) -> Model:
    """Authenticate via *guard_name* and return the guard's DB user instance."""
    from forgeapi.auth.facade import auth

    db_user = await auth.guard(guard_name).authenticate(request, required=True)

    if not getattr(db_user, "is_active", True):
        raise HTTPException(status_code=401, detail="User not found")

    return db_user


def require_permission(*permissions: str, guard: str | None = None):
    """FastAPI dependency — 403 if the authenticated user lacks any of the given permissions.

    Authenticates via *guard* (or the default guard when omitted), then calls
    :meth:`~forgeapi.permissions.PermissionsMixin.can` which tests both direct
    permissions and role-inherited ones.  Returns the DB user instance on
    success so the endpoint can use it directly.

    The *guard* name is forwarded to :meth:`~forgeapi.permissions.PermissionsMixin.can`
    so permission lookups are scoped to the correct namespace.

    Args:
        *permissions: One or more permission names. The user must hold
                      **at least one** of them (OR logic).
        guard:        Named auth guard to authenticate with.  Omit to use the
                      default guard.  Use when the controller uses a non-default
                      guard (e.g. ``guard="worker"`` resolves a ``Worker`` model
                      instead of ``User``).

    Raises:
        HTTPException 401: Missing / invalid credentials, or inactive user.
        HTTPException 403: User is active but holds none of the permissions.

    Example::

        @route.delete("/{id}")
        async def destroy(self, id: int, user=require_permission("delete:posts")):
            ...

        # Non-default guard (resolves Worker model, checks permissions in "worker" namespace):
        @route.post("/tasks")
        async def create_task(self, user=require_permission("create:tasks", guard="worker")):
            ...
    """
    async def _check(request: Request) -> Model:
        db_user = await _resolve_db_user(request, guard)
        if not await db_user.can(*permissions):
            raise HTTPException(status_code=403, detail="Forbidden")
        return db_user

    return Depends(_check)


def require_role(*roles: str, guard: str | None = None):
    """FastAPI dependency — 403 if the authenticated user lacks any of the given roles.

    Authenticates via *guard* (or the default guard when omitted), then calls
    :meth:`~forgeapi.permissions.PermissionsMixin.has_role` (OR logic).
    Returns the DB user instance on success so the endpoint can use it directly.

    Guard namespace is resolved automatically from the model's auth config registration —
    no need to pass it explicitly unless overriding.

    Args:
        *roles: One or more role names. The user must hold **at least one**
                of them (OR logic).
        guard:  Named auth guard to authenticate with.  Omit to use the
                default guard.

    Raises:
        HTTPException 401: Missing / invalid credentials, or inactive user.
        HTTPException 403: User is active but holds none of the roles.

    Example::

        @route.get("/admin/stats")
        async def stats(self, user=require_role("admin")):
            ...

        @route.get("/worker/dashboard")
        async def dashboard(self, user=require_role("supervisor", guard="worker")):
            ...
    """
    async def _check(request: Request) -> Model:
        db_user = await _resolve_db_user(request, guard)
        if not await db_user.has_role(*roles):
            raise HTTPException(status_code=403, detail="Forbidden")
        return db_user

    return Depends(_check)


# Backward-compatible aliases
RequirePermission = require_permission
RequireRole = require_role
