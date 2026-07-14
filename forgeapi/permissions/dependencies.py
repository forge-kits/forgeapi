from fastapi import Depends, HTTPException, Request
from tortoise.models import Model
from forgeapi.logging import log
from forgeapi.auth import CurrentUser
from .registry import get_user_model

_log = log.channel("permissions")

def require_permission(*permissions: str):
    """FastAPI dependency — 403 if the authenticated user lacks any of the given permissions.

    Resolves the DB user via the JWT sub claim, checks ``is_active``, then
    calls :meth:`~forgeapi.permissions.PermissionsMixin.can` which tests both
    direct permissions and role-inherited ones.  Returns the DB user instance
    on success so the endpoint can use it directly.

    Args:
        *permissions: One or more permission names.  The user must hold
                      **at least one** of them (OR logic).

    Returns:
        A FastAPI ``Depends`` object that resolves to the authenticated DB
        user model instance.

    Raises:
        HTTPException 401: Token sub is not a valid positive integer, or the
                           user no longer exists / is inactive.
        HTTPException 403: User is active but holds none of the permissions.

    Example::

        @route.delete("/{id}")
        async def destroy(self, id: int, user=require_permission("delete:posts")):
            ...

        # User must have AT LEAST ONE of the listed permissions:
        @route.post("/")
        async def create(self, payload: PostCreate, user=require_permission("create:posts", "admin")):
            ...
    """
    async def _check(auth_user: CurrentUser, request: Request) -> Model:
        UserModel = getattr(request.app.state, "user_model", None) or get_user_model()
        try:
            user_id = int(auth_user.id)
        except (TypeError, ValueError) as exc:
            _log.warning("Invalid user identity in token: %s", exc)
            raise HTTPException(status_code=401, detail="Invalid user identity")
        if user_id <= 0:
            raise HTTPException(status_code=401, detail="Invalid user identity")
        db_user = await UserModel.get_or_none(id=user_id)
        if not db_user:
            raise HTTPException(status_code=401, detail="User not found")
        if not getattr(db_user, "is_active", True):
            raise HTTPException(status_code=401, detail="User not found")
        if not await db_user.can(*permissions):
            raise HTTPException(status_code=403, detail="Forbidden")
        return db_user

    return Depends(_check)


def require_role(*roles: str):
    """FastAPI dependency — 403 if the authenticated user lacks any of the given roles.

    Resolves the DB user via the JWT sub claim, checks ``is_active``, then
    calls :meth:`~forgeapi.permissions.PermissionsMixin.has_role` (OR logic).
    Returns the DB user instance on success so the endpoint can use it directly.

    Args:
        *roles: One or more role names.  The user must hold **at least one**
                of them (OR logic).

    Returns:
        A FastAPI ``Depends`` object that resolves to the authenticated DB
        user model instance.

    Raises:
        HTTPException 401: Token sub is not a valid positive integer, or the
                           user no longer exists / is inactive.
        HTTPException 403: User is active but holds none of the roles.

    Example::

        @route.get("/admin/stats")
        async def stats(self, user=require_role("admin")):
            ...

        # User must have AT LEAST ONE of the listed roles:
        @route.get("/dashboard")
        async def dashboard(self, user=require_role("admin", "moderator")):
            ...
    """
    async def _check(auth_user: CurrentUser, request: Request) -> Model:
        UserModel = getattr(request.app.state, "user_model", None) or get_user_model()
        try:
            user_id = int(auth_user.id)
        except (TypeError, ValueError) as exc:
            _log.warning("Invalid user identity in token: %s", exc)
            raise HTTPException(status_code=401, detail="Invalid user identity")
        if user_id <= 0:
            raise HTTPException(status_code=401, detail="Invalid user identity")
        db_user = await UserModel.get_or_none(id=user_id)
        if not db_user:
            raise HTTPException(status_code=401, detail="User not found")
        if not getattr(db_user, "is_active", True):
            raise HTTPException(status_code=401, detail="User not found")
        if not await db_user.has_role(*roles):
            raise HTTPException(status_code=403, detail="Forbidden")
        return db_user

    return Depends(_check)


# Backward-compatible aliases
RequirePermission = require_permission
RequireRole = require_role
