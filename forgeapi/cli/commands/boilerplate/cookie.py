from __future__ import annotations

# ══════════════════════════════════════════════════════════════════════════════
# Schemas
# ══════════════════════════════════════════════════════════════════════════════

_SCHEMA_USER = """\
from pydantic import BaseModel
from forgeapi import BaseSchema


class UserResponse(BaseSchema):
    username:  str
    email:     str
    is_active: bool


class RegisterSchema(BaseModel):
    username: str
    email:    str
    password: str


class LoginSchema(BaseModel):
    username: str
    password: str
"""

# ══════════════════════════════════════════════════════════════════════════════
# Controller
# ══════════════════════════════════════════════════════════════════════════════

_CONTROLLER_USER = """\
from fastapi import HTTPException, Request, Response
from forgeapi.auth import CurrentUser, auth
from forgeapi.permissions import require_role
from forgeapi.controllers import Controller, route
from database.models import User
from app.schemas.user import UserResponse, RegisterSchema, LoginSchema
from app.events.user_registered_event import UserRegisteredEvent


class UserController(Controller):
    prefix = "/users"
    tags   = ["users"]
    schema = UserResponse

    @route.post("/register", status_code=201, summary="Register → sets session cookie")
    async def register(self, payload: RegisterSchema, response: Response) -> dict:
        if await User.filter(username=payload.username).exists():
            raise HTTPException(400, "Username already taken")
        if await User.filter(email=payload.email).exists():
            raise HTTPException(400, "Email already registered")
        user = User(username=payload.username, email=payload.email)
        user.set_password(payload.password)
        await user.save()
        await UserRegisteredEvent(user_id=user.id, username=user.username, email=user.email).dispatch()
        auth.set_cookie(response, {"sub": str(user.id), "username": user.username})
        return {"detail": "registered"}

    @route.post("/login", summary="Login → sets session cookie")
    async def login(self, payload: LoginSchema, response: Response) -> dict:
        user = await User.get_or_none(username=payload.username, is_active=True)
        if not user or not user.verify_password(payload.password):
            raise HTTPException(401, "Invalid credentials")
        auth.set_cookie(response, {"sub": str(user.id), "username": user.username})
        return {"detail": "logged in"}

    @route.post("/logout", summary="Logout → clears session cookie")
    async def logout(self, response: Response) -> dict:
        auth.delete_cookie(response)
        return {"detail": "logged out"}

    @route.get("/me", response_model=UserResponse, summary="Current user (cookie auth)")
    async def me(self, user: CurrentUser) -> UserResponse:
        return UserResponse.model_validate(await User.find_or_fail(int(user.id)))

    @route.get("/", response_model=None, summary="List users (admin only)")
    async def index(self, request: Request, user=require_role("admin")):
        return await User.all().order_by("-created_at").paginate(request, UserResponse)
"""
