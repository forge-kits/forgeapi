from __future__ import annotations

# ══════════════════════════════════════════════════════════════════════════════
# User model
# ══════════════════════════════════════════════════════════════════════════════

_MODEL_USER = """\
from tortoise import fields
from tortoise.models import Model
from forgeapi import ModelMixin


class User(ModelMixin, Model):
    id          = fields.IntField(pk=True)
    telegram_id = fields.BigIntField(unique=True)
    username    = fields.CharField(max_length=150, null=True)
    first_name  = fields.CharField(max_length=150, null=True)
    last_name   = fields.CharField(max_length=150, null=True)
    is_active   = fields.BooleanField(default=True)
    created_at  = fields.DatetimeField(auto_now_add=True)
    updated_at  = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "users"
"""

# ══════════════════════════════════════════════════════════════════════════════
# Schemas
# ══════════════════════════════════════════════════════════════════════════════

_SCHEMA_USER = """\
from forgeapi import BaseSchema


class UserResponse(BaseSchema):
    telegram_id: int
    username:    str | None
    first_name:  str | None
    last_name:   str | None
    is_active:   bool
"""

# ══════════════════════════════════════════════════════════════════════════════
# UserFirstLogin event
# ══════════════════════════════════════════════════════════════════════════════

_EVENT_USER_FIRST_LOGIN = """\
from forgeapi import Event


class UserFirstLoginEvent(Event):
    background = True

    def __init__(self, user_id: int, telegram_id: int, username: str | None) -> None:
        self.user_id     = user_id
        self.telegram_id = telegram_id
        self.username    = username
"""

_EVENTS_INIT = """\
from .user_first_login_event import UserFirstLoginEvent
from .post_created_event import PostCreatedEvent
"""

# ══════════════════════════════════════════════════════════════════════════════
# Listener
# ══════════════════════════════════════════════════════════════════════════════

_LISTENER_USER = """\
from forgeapi import listen, Log
from app.events.user_first_login_event import UserFirstLoginEvent


@listen(UserFirstLoginEvent)
async def on_first_login(event: UserFirstLoginEvent) -> None:
    Log.info("User first login",
             user_id=event.user_id, telegram_id=event.telegram_id, username=event.username)
    # Add: send welcome message, grant default role, etc.
"""

# ══════════════════════════════════════════════════════════════════════════════
# User controller
# ══════════════════════════════════════════════════════════════════════════════

_CONTROLLER_USER = """\
from fastapi import Request
from forgeapi.auth import CurrentUser
from forgeapi.controllers import Controller, route
from database.models import User
from app.schemas.user import UserResponse
from app.events.user_first_login_event import UserFirstLoginEvent


class UserController(Controller):
    prefix = "/users"
    tags   = ["users"]
    schema = UserResponse

    @route.get("/me", response_model=UserResponse,
               summary="Current Telegram user (auto-registers on first call)")
    async def me(self, user: CurrentUser) -> UserResponse:
        db_user, created = await User.get_or_create(
            telegram_id=int(user.id),
            defaults={
                "username":   user.username,
                "first_name": user.extra.get("first_name"),
                "last_name":  user.extra.get("last_name"),
            },
        )
        if created:
            await UserFirstLoginEvent(
                user_id=db_user.id, telegram_id=int(user.id), username=user.username,
            ).dispatch()
        return UserResponse.model_validate(db_user)

    @route.get("/", response_model=None, summary="List users (paginated)")
    async def index(self, request: Request):
        return await User.all().order_by("-created_at").paginate(request, UserResponse)
"""

# ══════════════════════════════════════════════════════════════════════════════
# Post controller (Telegram — no policy, direct author check via telegram_id)
# ══════════════════════════════════════════════════════════════════════════════

_CONTROLLER_POST = """\
from fastapi import HTTPException, Request
from forgeapi import Cache
from forgeapi.auth import CurrentUser, OptionalUser
from forgeapi.controllers import Controller, route
from database.models import Post, User
from app.schemas.post import PostResponse, PostCreatePayload, PostUpdatePayload
from app.events.post_created_event import PostCreatedEvent


async def _resolve_author(user: CurrentUser) -> "User":
    db_user = await User.get_or_none(telegram_id=int(user.id))
    if not db_user:
        raise HTTPException(401, "Call GET /api/v1/users/me first to register your account")
    return db_user


class PostController(Controller):
    prefix = "/posts"
    tags   = ["posts"]
    schema = PostResponse

    @route.get("/", response_model=None, summary="List published posts (paginated)")
    async def index(self, request: Request):
        return await Post.filter(is_published=True).order_by("-created_at").paginate(request, PostResponse)

    @route.get("/popular", response_model=None, summary="Top-10 popular posts (cached 5 min)")
    async def popular(self, request: Request):
        return await Cache.remember(
            "posts:popular",
            fn=lambda: Post.filter(is_published=True).order_by("-views").limit(10),
            ttl=300,
        )

    @route.post("/", status_code=201, summary="Create post (Telegram auth)")
    async def create(self, payload: PostCreatePayload, user: CurrentUser):
        author = await _resolve_author(user)
        post = await Post.create_from(payload, author_id=author.id)
        await Cache.forget("posts:popular")
        await PostCreatedEvent(post_id=post.id, title=post.title, author_id=author.id).dispatch()
        return post

    @route.get("/{id}", summary="Get post by id")
    async def show(self, id: int, user: OptionalUser):
        post = await Post.find_or_fail(id)
        if not post.is_published:
            if user is None:
                raise HTTPException(404, "Post not found")
            author = await User.get_or_none(telegram_id=int(user.id))
            if not author or post.author_id != author.id:
                raise HTTPException(404, "Post not found")
        await Cache.increment(f"views:post:{id}")
        return post

    @route.patch("/{id}", summary="Update own post")
    async def update(self, id: int, payload: PostUpdatePayload, user: CurrentUser):
        author = await _resolve_author(user)
        post = await Post.find_or_fail(id)
        if post.author_id != author.id:
            raise HTTPException(403, "Not allowed")
        result = await post.update_from(payload)
        await Cache.forget("posts:popular")
        return result

    @route.delete("/{id}", status_code=204, summary="Delete own post")
    async def destroy(self, id: int, user: CurrentUser):
        author = await _resolve_author(user)
        post = await Post.find_or_fail(id)
        if post.author_id != author.id:
            raise HTTPException(403, "Not allowed")
        await post.delete()
        await Cache.forget("posts:popular")
"""

# ══════════════════════════════════════════════════════════════════════════════
# Seeder
# ══════════════════════════════════════════════════════════════════════════════

_SEEDER_USER = """\
from forgeapi.database import Seeder
from database.models import User


class UserSeeder(Seeder):
    async def run(self) -> None:
        await User.get_or_create(
            telegram_id=123456789,
            defaults={
                "username":   "demo_user",
                "first_name": "Demo",
                "last_name":  "User",
                "is_active":  True,
            },
        )
"""
