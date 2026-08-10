from __future__ import annotations

from fastapi import Depends, HTTPException, Request
from tortoise.models import Model
from forgeapi.logging import log
from .registry import get_user_model

_log = log.channel("permissions")


async def _resolve_db_user(request: Request, guard_name: str | None) -> Model:
    """Authenticate via *guard_name* and return a DB model instance.

    When the guard has ``user_model`` configured it returns the DB record
    directly.  When it returns a bare ``AuthUser`` DTO (no model on the guard),
    we fall back to the global registry / ``app.state.user_model``.
    """
    from forgeapi.auth.facade import auth
    from forgeapi.auth.models import AuthUser

    _guard = auth.guard(guard_name)
    db_user = await _guard.authenticate(request, required=True)

    if isinstance(db_user, AuthUser):
        UserModel = getattr(request.app.state, "user_model", None) or get_user_model()
        try:
            user_id = int(db_user.id)
        except (TypeError, ValueError) as exc:
            _log.warning("Invalid user identity in token: %s", exc)
            raise HTTPException(status_code=401, detail="Invalid user identity")
        if user_id <= 0:
            raise HTTPException(status_code=401, detail="Invalid user identity")
        db_user = await UserModel.get_or_none(pk=user_id)
        if not db_user:
            raise HTTPException(status_code=401, detail="User not found")

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
    _guard_name = guard or "api"

    async def _check(request: Request) -> Model:
        db_user = await _resolve_db_user(request, guard)
        if not await db_user.can(*permissions, guard=_guard_name):
            raise HTTPException(status_code=403, detail="Forbidden")
        return db_user

    return Depends(_check)


def require_role(*roles: str, guard: str | None = None):
    """FastAPI dependency — 403 if the authenticated user lacks any of the given roles.

    Authenticates via *guard* (or the default guard when omitted), then calls
    :meth:`~forgeapi.permissions.PermissionsMixin.has_role` (OR logic).
    Returns the DB user instance on success so the endpoint can use it directly.

    The *guard* name is forwarded to :meth:`~forgeapi.permissions.PermissionsMixin.has_role`
    so role lookups are scoped to the correct namespace.

    Args:
        *roles: One or more role names. The user must hold **at least one**
                of them (OR logic).
        guard:  Named auth guard to authenticate with.  Omit to use the
                default guard.  Use when the controller uses a non-default
                guard (e.g. ``guard="worker"`` resolves a ``Worker`` model
                instead of ``User``).

    Raises:
        HTTPException 401: Missing / invalid credentials, or inactive user.
        HTTPException 403: User is active but holds none of the roles.

    Example::

        @route.get("/admin/stats")
        async def stats(self, user=require_role("admin")):
            ...

        # Non-default guard (resolves Worker model, checks roles in "worker" namespace):
        @route.get("/worker/dashboard")
        async def dashboard(self, user=require_role("supervisor", guard="worker")):
            ...
    """
    _guard_name = guard or "api"

    async def _check(request: Request) -> Model:
        db_user = await _resolve_db_user(request, guard)
        if not await db_user.has_role(*roles, guard=_guard_name):
            raise HTTPException(status_code=403, detail="Forbidden")
        return db_user

    return Depends(_check)


# Backward-compatible aliases
RequirePermission = require_permission
RequireRole = require_role
