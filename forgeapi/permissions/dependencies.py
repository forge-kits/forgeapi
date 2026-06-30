import logging

from fastapi import Depends, HTTPException

from forgeapi.auth import CurrentUser
from .registry import get_user_model

logger = logging.getLogger("forgeapi.permissions")


def RequirePermission(*permissions: str):
    """403 if the authenticated user lacks any of the given permissions.

    Returns the DB user instance on success.

    Usage::

        @route.delete("/{id}")
        async def destroy(self, id: int, user=RequirePermission("delete:posts")):
            ...

        # user must have AT LEAST ONE
        @route.post("/")
        async def create(self, payload: PostCreate, user=RequirePermission("create:posts", "admin")):
            ...
    """
    async def _check(auth_user: CurrentUser):
        UserModel = get_user_model()
        db_user = await UserModel.get_or_none(id=int(auth_user.id))
        if not db_user:
            raise HTTPException(status_code=403, detail="User not found")
        if not await db_user.can(*permissions):
            raise HTTPException(
                status_code=403,
                detail=f"Missing permission: {', '.join(permissions)}",
            )
        return db_user

    return Depends(_check)


def RequireRole(*roles: str):
    """403 if the authenticated user lacks any of the given roles.

    Returns the DB user instance on success.

    Usage::

        @route.get("/admin/stats")
        async def stats(self, user=RequireRole("admin")):
            ...

        # user must have AT LEAST ONE
        @route.get("/dashboard")
        async def dashboard(self, user=RequireRole("admin", "moderator")):
            ...
    """
    async def _check(auth_user: CurrentUser):
        UserModel = get_user_model()
        db_user = await UserModel.get_or_none(id=int(auth_user.id))
        if not db_user:
            raise HTTPException(status_code=403, detail="User not found")
        if not await db_user.has_role(*roles):
            raise HTTPException(
                status_code=403,
                detail=f"Required role: {', '.join(roles)}",
            )
        return db_user

    return Depends(_check)
