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


class TokenSchema(BaseModel):
    access_token:  str
    refresh_token: str
    token_type:    str = "bearer"


class RefreshSchema(BaseModel):
    refresh_token: str
"""

# ══════════════════════════════════════════════════════════════════════════════
# Controller
# ══════════════════════════════════════════════════════════════════════════════

_CONTROLLER_USER = """\
from fastapi import HTTPException, Request
from forgeapi.auth import CurrentUser, auth
from forgeapi.exceptions import TokenExpiredError, TokenInvalidError
from forgeapi.permissions import require_role
from forgeapi.controllers import Controller, route
from database.models import User
from app.schemas.user import UserResponse, RegisterSchema, LoginSchema, TokenSchema, RefreshSchema
from app.events.user_registered_event import UserRegisteredEvent


class UserController(Controller):
    prefix = "/users"
    tags   = ["users"]
    schema = UserResponse

    @route.post("/register", response_model=TokenSchema, status_code=201, summary="Register")
    async def register(self, payload: RegisterSchema) -> TokenSchema:
        if await User.filter(username=payload.username).exists():
            raise HTTPException(400, "Username already taken")
        if await User.filter(email=payload.email).exists():
            raise HTTPException(400, "Email already registered")
        user = User(username=payload.username, email=payload.email)
        user.set_password(payload.password)
        await user.save()
        await UserRegisteredEvent(user_id=user.id, username=user.username, email=user.email).dispatch()
        return TokenSchema(access_token=auth.token(user), refresh_token=auth.refresh_token(user))

    @route.post("/login", response_model=TokenSchema, summary="Login → JWT tokens")
    async def login(self, payload: LoginSchema) -> TokenSchema:
        user = await User.get_or_none(username=payload.username, is_active=True)
        if not user or not user.verify_password(payload.password):
            raise HTTPException(401, "Invalid credentials")
        return TokenSchema(access_token=auth.token(user), refresh_token=auth.refresh_token(user))

    @route.post("/refresh", response_model=TokenSchema, summary="Refresh access token")
    async def refresh_token(self, payload: RefreshSchema) -> TokenSchema:
        try:
            data = auth.decode(payload.refresh_token, expected_type="refresh")
        except (TokenExpiredError, TokenInvalidError) as e:
            raise HTTPException(401, str(e))
        user = await User.find_or_fail(int(data["sub"]))
        return TokenSchema(access_token=auth.token(user), refresh_token=payload.refresh_token)

    @route.get("/me", response_model=UserResponse, summary="Current user")
    async def me(self, user: CurrentUser) -> UserResponse:
        return UserResponse.model_validate(await User.find_or_fail(int(user.id)))

    @route.get("/", response_model=None, summary="List users (admin only)")
    async def index(self, request: Request, user=require_role("admin")):
        return await User.all().order_by("-created_at").paginate(request, UserResponse)
"""
