from __future__ import annotations

# ══════════════════════════════════════════════════════════════════════════════
# Post model
# ══════════════════════════════════════════════════════════════════════════════

_MODELS_INIT = """\
from .user import User
from .post import Post
"""

_MODEL_POST = """\
from tortoise import fields
from tortoise.models import Model
from forgeapi import ModelMixin


class Post(ModelMixin, Model):
    id           = fields.IntField(pk=True)
    title        = fields.CharField(max_length=255)
    body         = fields.TextField()
    is_published = fields.BooleanField(default=True)
    views        = fields.IntField(default=0)
    author_id    = fields.IntField()
    created_at   = fields.DatetimeField(auto_now_add=True)
    updated_at   = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "posts"
"""

# ══════════════════════════════════════════════════════════════════════════════
# Post schemas
# ══════════════════════════════════════════════════════════════════════════════

_SCHEMA_POST = """\
from forgeapi import BaseSchema, BaseCreateSchema, BaseUpdateSchema


class PostResponse(BaseSchema):
    title:        str
    body:         str
    is_published: bool
    views:        int
    author_id:    int


class PostCreatePayload(BaseCreateSchema):
    title:        str
    body:         str
    is_published: bool = True


class PostUpdatePayload(BaseUpdateSchema):
    title:        str | None = None
    body:         str | None = None
    is_published: bool | None = None
"""

# ══════════════════════════════════════════════════════════════════════════════
# Post event
# ══════════════════════════════════════════════════════════════════════════════

_EVENT_POST_CREATED = """\
from forgeapi import Event


class PostCreatedEvent(Event):
    background = True
    # Uncomment to publish across workers via Redis:
    # redis      = True
    # redis_type = "pubsub"   # fan-out: all workers get it
    # redis_type = "stream"   # persistent: consumer groups, survives restarts
    # ttl        = 60         # pubsub dedup: one worker per event_id per 60s

    def __init__(self, post_id: int, title: str, author_id: int) -> None:
        self.post_id   = post_id
        self.title     = title
        self.author_id = author_id
"""

# ══════════════════════════════════════════════════════════════════════════════
# Post listener
# ══════════════════════════════════════════════════════════════════════════════

_LISTENER_POST = """\
from forgeapi import listen, Log
from app.events.post_created_event import PostCreatedEvent


@listen(PostCreatedEvent)
async def on_post_created(event: PostCreatedEvent) -> None:
    Log.info("Post created", post_id=event.post_id, title=event.title, author_id=event.author_id)
    # Add: send notification, update search index, push to Telegram, etc.
"""

# ══════════════════════════════════════════════════════════════════════════════
# Post policy
# ══════════════════════════════════════════════════════════════════════════════

_POST_POLICY = """\
from forgeapi import Policy, gate
from database.models import Post


@gate.policy(Post)
class PostPolicy(Policy):
    async def before(self, user, action: str):
        # Return True to grant all actions (e.g. admin bypass via require_role dependency)
        return None

    async def view(self, user, post) -> bool:
        if user is None:
            return post.is_published
        return post.is_published or post.author_id == int(user.id)

    async def create(self, user) -> bool:
        return user is not None

    async def update(self, user, post) -> bool:
        return post.author_id == int(user.id)

    async def delete(self, user, post) -> bool:
        return post.author_id == int(user.id)
"""

# ══════════════════════════════════════════════════════════════════════════════
# Post controller (JWT + Cookie)
# ══════════════════════════════════════════════════════════════════════════════

_CONTROLLER_POST_STD = """\
from fastapi import Request
from forgeapi import Cache, gate
from forgeapi.auth import CurrentUser, OptionalUser
from forgeapi.controllers import Controller, route
from database.models import Post
from app.schemas.post import PostResponse, PostCreatePayload, PostUpdatePayload
from app.events.post_created_event import PostCreatedEvent


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

    @route.post("/", status_code=201, summary="Create post (auth required)")
    async def create(self, payload: PostCreatePayload, user: CurrentUser):
        await gate.authorize(user, "create", Post)
        post = await Post.create_from(payload, author_id=int(user.id))
        await Cache.forget("posts:popular")
        await PostCreatedEvent(post_id=post.id, title=post.title, author_id=int(user.id)).dispatch()
        return post

    @route.get("/{id}", summary="Get post by id")
    async def show(self, id: int, user: OptionalUser):
        post = await Post.find_or_fail(id)
        await gate.authorize(user, "view", post)
        await Cache.increment(f"views:post:{id}")
        return post

    @route.patch("/{id}", summary="Update own post")
    async def update(self, id: int, payload: PostUpdatePayload, user: CurrentUser):
        post = await Post.find_or_fail(id)
        await gate.authorize(user, "update", post)
        result = await post.update_from(payload)
        await Cache.forget("posts:popular")
        return result

    @route.delete("/{id}", status_code=204, summary="Delete own post")
    async def destroy(self, id: int, user: CurrentUser):
        post = await Post.find_or_fail(id)
        await gate.authorize(user, "delete", post)
        await post.delete()
        await Cache.forget("posts:popular")
"""

# ══════════════════════════════════════════════════════════════════════════════
# Post seeder
# ══════════════════════════════════════════════════════════════════════════════

_SEEDER_POST = """\
from forgeapi.database import Seeder
from database.models import Post, User


class PostSeeder(Seeder):
    async def run(self) -> None:
        user = await User.first()
        if not user:
            return
        posts = [
            ("Hello World",     "Welcome to forge-kits! This is your first post."),
            ("Getting Started", "Edit app/controllers/post_controller.py to customize this API."),
            ("Event System",    "PostCreatedEvent fires on every new post — check app/listeners/."),
        ]
        for title, body in posts:
            await Post.get_or_create(
                title=title,
                defaults={"body": body, "is_published": True, "author_id": user.id},
            )
"""

# ══════════════════════════════════════════════════════════════════════════════
# Password-based User model (JWT + Cookie)
# ══════════════════════════════════════════════════════════════════════════════

_MODEL_USER_PASSWORD = """\
import hashlib
import os
from tortoise import fields
from tortoise.models import Model
from forgeapi import ModelMixin
from forgeapi.permissions import PermissionsMixin


class User(ModelMixin, PermissionsMixin, Model):
    id            = fields.IntField(pk=True)
    username      = fields.CharField(max_length=150, unique=True)
    email         = fields.CharField(max_length=255, unique=True)
    password_hash = fields.CharField(max_length=255)
    is_active     = fields.BooleanField(default=True)
    created_at    = fields.DatetimeField(auto_now_add=True)
    updated_at    = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "users"

    def set_password(self, raw: str) -> None:
        salt = os.urandom(16).hex()
        self.password_hash = salt + ":" + hashlib.sha256(f"{raw}{salt}".encode()).hexdigest()

    def verify_password(self, raw: str) -> bool:
        salt, hashed = self.password_hash.split(":", 1)
        return hashlib.sha256(f"{raw}{salt}".encode()).hexdigest() == hashed
"""

# ══════════════════════════════════════════════════════════════════════════════
# UserRegistered event (JWT + Cookie)
# ══════════════════════════════════════════════════════════════════════════════

_EVENT_USER_REGISTERED = """\
from forgeapi import Event


class UserRegisteredEvent(Event):
    background = True
    # redis = True  # uncomment to publish to Redis

    def __init__(self, user_id: int, username: str, email: str) -> None:
        self.user_id  = user_id
        self.username = username
        self.email    = email
"""

_EVENTS_INIT_PASSWORD = """\
from .user_registered_event import UserRegisteredEvent
from .post_created_event import PostCreatedEvent
"""

# ══════════════════════════════════════════════════════════════════════════════
# User listener (JWT + Cookie)
# ══════════════════════════════════════════════════════════════════════════════

_LISTENER_USER_PASSWORD = """\
from forgeapi import listen, Log
from app.events.user_registered_event import UserRegisteredEvent


@listen(UserRegisteredEvent)
async def on_user_registered(event: UserRegisteredEvent) -> None:
    Log.info("User registered", user_id=event.user_id, username=event.username, email=event.email)
    # Add: send welcome email, create default settings, etc.
"""

# ══════════════════════════════════════════════════════════════════════════════
# User seeder (JWT + Cookie) — with roles and permissions
# ══════════════════════════════════════════════════════════════════════════════

_SEEDER_USER_PASSWORD = """\
from forgeapi.database import Seeder
from forgeapi.permissions.models import Role
from database.models import User


class UserSeeder(Seeder):
    async def run(self) -> None:
        # ── Roles and permissions ─────────────────────────────────────────────
        admin_role = await Role.find_or_create("admin")
        await admin_role.give_permission(
            "manage:users", "create:posts", "edit:posts", "delete:posts"
        )

        user_role = await Role.find_or_create("user")
        await user_role.give_permission("create:posts")

        # ── Admin account  (login: admin / admin123) ──────────────────────────
        admin, created = await User.get_or_create(
            username="admin",
            defaults={"email": "admin@example.com", "password_hash": "", "is_active": True},
        )
        if created:
            admin.set_password("admin123")
            await admin.save()
            await admin.assign_role("admin")

        # ── Regular user  (login: user / user123) ─────────────────────────────
        user, created = await User.get_or_create(
            username="user",
            defaults={"email": "user@example.com", "password_hash": "", "is_active": True},
        )
        if created:
            user.set_password("user123")
            await user.save()
            await user.assign_role("user")
"""

# ══════════════════════════════════════════════════════════════════════════════
# Seeds __init__.py — registers seeders for `forgeapi db:seed`
# ══════════════════════════════════════════════════════════════════════════════

_SEEDS_INIT = """\
from .user_seeder import UserSeeder
from .post_seeder import PostSeeder

__all__ = ["UserSeeder", "PostSeeder"]
"""

# ══════════════════════════════════════════════════════════════════════════════
# RedisBus cross-service example (app/bus.py)
# ══════════════════════════════════════════════════════════════════════════════

_BUS_EXAMPLE = """\
# Cross-service event bridge via Redis (RedisBus).
# Lets separate projects communicate over a shared Redis channel.
# Uncomment and set REDIS_URL in .env to activate.
#
# import os
# from forgeapi import RedisBus
#
# bus = RedisBus(os.getenv("REDIS_URL", "redis://localhost:6379"), namespace="myapp")
#
# @bus.on("order:created")
# async def on_order_created_external(data: dict) -> None:
#     # Triggered when another service emits "order:created" on Redis
#     print(f"New order from external service: {data}")
#
# ── Wire in main.py lifespan ──────────────────────────────────────────────────
# from contextlib import asynccontextmanager
# from fastapi import FastAPI
# from app.bus import bus
#
# @asynccontextmanager
# async def lifespan(app: FastAPI):
#     async with bus:
#         yield
#
# app = FastAPI(lifespan=lifespan)
"""
