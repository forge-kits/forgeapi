from fastapi import Depends, HTTPException


def RequirePermission(*permissions: str):
    """FastAPI dependency — 403 if the authenticated user lacks any of the permissions.

    Returns the DB user instance on success.

    Usage::

        from forgeapi.permissions import RequirePermission

        @router.delete("/{post_id}")
        async def destroy(post_id: int, user=RequirePermission("delete:posts")):
            ...

        # multiple — user must have AT LEAST ONE
        @router.post("/")
        async def create(payload: PostCreate, user=RequirePermission("create:posts", "admin")):
            ...
    """
    from forgeapi.auth import CurrentUser
    from .registry import get_user_model

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
    """FastAPI dependency — 403 if the authenticated user lacks any of the roles.

    Returns the DB user instance on success.

    Usage::

        from forgeapi.permissions import RequireRole

        @router.get("/admin/stats")
        async def stats(user=RequireRole("admin")):
            ...

        # multiple — user must have AT LEAST ONE of the roles
        @router.get("/dashboard")
        async def dashboard(user=RequireRole("admin", "moderator")):
            ...
    """
    from forgeapi.auth import CurrentUser
    from .registry import get_user_model

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
