from pathlib import Path

# ══════════════════════════════════════════════════════════════════════════════
# Shared — models
# ══════════════════════════════════════════════════════════════════════════════

_MODELS_INIT = """\
from .user import User
from .post import Post
"""

_MODEL_POST = """\
from tortoise import fields
from tortoise.models import Model


class Post(Model):
    title        = fields.CharField(max_length=255)
    body         = fields.TextField()
    author       = fields.ForeignKeyField("models.User", related_name="posts", on_delete=fields.CASCADE)
    is_published = fields.BooleanField(default=True)
    created_at   = fields.DatetimeField(auto_now_add=True)
    updated_at   = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "posts"
"""

# ── Shared — schemas ──────────────────────────────────────────────────────────

_SCHEMA_POST_RESPONSE = """\
from pydantic import BaseModel
from forgeapi import BaseSchema


class PostResponse(BaseSchema):
    title:        str
    body:         str
    is_published: bool
    author_id:    int


class PostListResponse(BaseModel):
    items: list[PostResponse]
    total: int
"""

_SCHEMA_POST_PAYLOAD = """\
from forgeapi import BaseCreateSchema, BaseUpdateSchema


class PostCreatePayload(BaseCreateSchema):
    title:        str
    body:         str
    is_published: bool = True


class PostUpdatePayload(BaseUpdateSchema):
    title:        str | None = None
    body:         str | None = None
    is_published: bool | None = None
"""

# ── Shared — events ───────────────────────────────────────────────────────────

_EVENT_POST_CREATED = """\
from forgeapi import Event


class PostCreatedEvent(Event):
    background = True
    # redis      = True          # uncomment to publish to Redis
    # redis_type = "pubsub"      # "pubsub" = fan-out to all workers (default)
    # redis_type = "stream"      # "stream" = persistent, consumer groups (XADD/XREADGROUP)
    # namespace  = "forgeapi:events"  # Redis key prefix: {namespace}:{ClassName}
    # ttl        = 60            # pubsub dedup: only first worker processes per 60s window

    def __init__(self, post_id: int, title: str, author_id: int) -> None:
        self.post_id   = post_id
        self.title     = title
        self.author_id = author_id
"""

_LISTENER_POST = """\
import logging
from forgeapi import listen
from app.events.post_created_event import PostCreatedEvent

logger = logging.getLogger("app")


@listen(PostCreatedEvent)
async def on_post_created(event: PostCreatedEvent) -> None:
    logger.info("[event] PostCreated  id=%d  title='%s'  author_id=%d",
                event.post_id, event.title, event.author_id)
"""

# ══════════════════════════════════════════════════════════════════════════════
# JWT
# ══════════════════════════════════════════════════════════════════════════════

_MODEL_USER_PASSWORD = """\
from tortoise import fields
from tortoise.models import Model


class User(Model):
    username      = fields.CharField(max_length=150, unique=True)
    email         = fields.CharField(max_length=255, unique=True)
    password_hash = fields.CharField(max_length=255)
    is_active     = fields.BooleanField(default=True)
    created_at    = fields.DatetimeField(auto_now_add=True)
    updated_at    = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "users"
"""

_UTILS_PASSWORD = """\
import hashlib
import os


def hash_password(password: str) -> str:
    salt = os.urandom(16).hex()
    return salt + ":" + hashlib.sha256(f"{password}{salt}".encode()).hexdigest()


def verify_password(password: str, password_hash: str) -> bool:
    salt, hashed = password_hash.split(":", 1)
    return hashlib.sha256(f"{password}{salt}".encode()).hexdigest() == hashed
"""

_SCHEMA_USER_PASSWORD = """\
from pydantic import BaseModel
from forgeapi import BaseSchema


class UserResponse(BaseSchema):
    username:  str
    email:     str
    is_active: bool


class UserListResponse(BaseModel):
    items: list[UserResponse]
    total: int


class RegisterSchema(BaseModel):
    username: str
    email:    str
    password: str


class LoginSchema(BaseModel):
    username: str
    password: str


class TokenSchema(BaseModel):
    access_token: str
    token_type:   str = "bearer"
"""

_EVENT_USER_REGISTERED = """\
from forgeapi import Event


class UserRegisteredEvent(Event):
    background = True

    def __init__(self, user_id: int, username: str, email: str) -> None:
        self.user_id  = user_id
        self.username = username
        self.email    = email
"""

_EVENTS_INIT_PASSWORD = """\
from .user_registered_event import UserRegisteredEvent
from .post_created_event import PostCreatedEvent
"""

_LISTENER_USER_PASSWORD = """\
import logging
from forgeapi import listen
from app.events.user_registered_event import UserRegisteredEvent

logger = logging.getLogger("app")


@listen(UserRegisteredEvent)
async def on_user_registered(event: UserRegisteredEvent) -> None:
    logger.info("[event] UserRegistered  id=%d  username=%s  email=%s",
                event.user_id, event.username, event.email)
"""

_CONTROLLER_USER_JWT = """\
import os
import jwt
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException
from forgeapi.auth import CurrentUser
from forgeapi.pagination import Pagination
from .controller import Controller, route
from database.models import User
from app.schemas.user import UserResponse, UserListResponse, RegisterSchema, LoginSchema, TokenSchema
from app.events.user_registered_event import UserRegisteredEvent
from app.utils import hash_password, verify_password


def _make_token(user_id: int, username: str) -> str:
    exp = datetime.now(timezone.utc) + timedelta(minutes=30)
    return jwt.encode(
        {"sub": str(user_id), "username": username, "exp": exp, "type": "access"},
        os.getenv("JWT_SECRET", ""),
        algorithm="HS256",
    )


class UserController(Controller):
    prefix = "/users"
    tags   = ["users"]

    @route.post("/register", response_model=TokenSchema, summary="Register")
    async def register(self, payload: RegisterSchema) -> TokenSchema:
        if await User.filter(username=payload.username).exists():
            raise HTTPException(400, "Username already taken")
        if await User.filter(email=payload.email).exists():
            raise HTTPException(400, "Email already registered")
        user = await User.create(
            username=payload.username,
            email=payload.email,
            password_hash=hash_password(payload.password),
        )
        await UserRegisteredEvent(user_id=user.id, username=user.username, email=user.email).dispatch()
        return TokenSchema(access_token=_make_token(user.id, user.username))

    @route.post("/login", response_model=TokenSchema, summary="Login → JWT token")
    async def login(self, payload: LoginSchema) -> TokenSchema:
        user = await User.filter(username=payload.username, is_active=True).first()
        if not user or not verify_password(payload.password, user.password_hash):
            raise HTTPException(401, "Invalid credentials")
        return TokenSchema(access_token=_make_token(user.id, user.username))

    @route.get("/me", response_model=UserResponse, summary="Current user (Bearer token)")
    async def me(self, user: CurrentUser) -> UserResponse:
        db_user = await User.get_or_none(id=int(user.id))
        if not db_user:
            raise HTTPException(404, "User not found")
        return UserResponse.model_validate(db_user)

    @route.get("/", response_model=UserListResponse, summary="List users with pagination")
    async def index(self, pagination: Pagination) -> UserListResponse:
        total = await User.all().count()
        users = await User.all().offset(pagination.offset).limit(pagination.limit)
        return UserListResponse(items=[UserResponse.model_validate(u) for u in users], total=total)
"""

# ── Cookie ────────────────────────────────────────────────────────────────────

_CONTROLLER_USER_COOKIE = """\
from fastapi import HTTPException, Response
from forgeapi.auth import CurrentUser, auth
from forgeapi.pagination import Pagination
from .controller import Controller, route
from database.models import User
from app.schemas.user import UserResponse, UserListResponse, RegisterSchema, LoginSchema
from app.events.user_registered_event import UserRegisteredEvent
from app.utils import hash_password, verify_password


class UserController(Controller):
    prefix = "/users"
    tags   = ["users"]

    @route.post("/register", summary="Register → sets session cookie")
    async def register(self, payload: RegisterSchema, response: Response) -> dict:
        if await User.filter(username=payload.username).exists():
            raise HTTPException(400, "Username already taken")
        if await User.filter(email=payload.email).exists():
            raise HTTPException(400, "Email already registered")
        user = await User.create(
            username=payload.username,
            email=payload.email,
            password_hash=hash_password(payload.password),
        )
        await UserRegisteredEvent(user_id=user.id, username=user.username, email=user.email).dispatch()
        auth.set_cookie(response, {"sub": str(user.id), "username": user.username})
        return {"detail": "registered"}

    @route.post("/login", summary="Login → sets session cookie")
    async def login(self, payload: LoginSchema, response: Response) -> dict:
        user = await User.filter(username=payload.username, is_active=True).first()
        if not user or not verify_password(payload.password, user.password_hash):
            raise HTTPException(401, "Invalid credentials")
        auth.set_cookie(response, {"sub": str(user.id), "username": user.username})
        return {"detail": "logged in"}

    @route.post("/logout", summary="Logout → clears session cookie")
    async def logout(self, response: Response) -> dict:
        auth.delete_cookie(response)
        return {"detail": "logged out"}

    @route.get("/me", response_model=UserResponse, summary="Current user (cookie auth)")
    async def me(self, user: CurrentUser) -> UserResponse:
        db_user = await User.get_or_none(id=int(user.id))
        if not db_user:
            raise HTTPException(404, "User not found")
        return UserResponse.model_validate(db_user)

    @route.get("/", response_model=UserListResponse, summary="List users with pagination")
    async def index(self, pagination: Pagination) -> UserListResponse:
        total = await User.all().count()
        users = await User.all().offset(pagination.offset).limit(pagination.limit)
        return UserListResponse(items=[UserResponse.model_validate(u) for u in users], total=total)
"""

# ── Post controller (JWT + Cookie) ────────────────────────────────────────────

_CONTROLLER_POST_STD = """\
from fastapi import HTTPException
from forgeapi.auth import CurrentUser
from forgeapi.pagination import Pagination
from .controller import Controller, route
from database.models import Post
from app.schemas.response.post import PostResponse, PostListResponse
from app.schemas.payload.post import PostCreatePayload, PostUpdatePayload
from app.events.post_created_event import PostCreatedEvent


class PostController(Controller):
    prefix = "/posts"
    tags   = ["posts"]

    @route.get("/", response_model=PostListResponse, summary="List published posts")
    async def index(self, pagination: Pagination) -> PostListResponse:
        total = await Post.filter(is_published=True).count()
        posts = await Post.filter(is_published=True).offset(pagination.offset).limit(pagination.limit)
        return PostListResponse(items=[PostResponse.model_validate(p) for p in posts], total=total)

    @route.post("/", response_model=PostResponse, summary="Create post (auth required)")
    async def create(self, payload: PostCreatePayload, user: CurrentUser) -> PostResponse:
        post = await Post.create(
            title=payload.title,
            body=payload.body,
            is_published=payload.is_published,
            author_id=int(user.id),
        )
        await PostCreatedEvent(post_id=post.id, title=post.title, author_id=int(user.id)).dispatch()
        return PostResponse.model_validate(post)

    @route.get("/{post_id}", response_model=PostResponse, summary="Get post by id")
    async def show(self, post_id: int) -> PostResponse:
        post = await Post.get_or_none(id=post_id, is_published=True)
        if not post:
            raise HTTPException(404, "Post not found")
        return PostResponse.model_validate(post)

    @route.patch("/{post_id}", response_model=PostResponse, summary="Update own post")
    async def update(self, post_id: int, payload: PostUpdatePayload, user: CurrentUser) -> PostResponse:
        post = await Post.get_or_none(id=post_id, author_id=int(user.id))
        if not post:
            raise HTTPException(404, "Post not found or not yours")
        for field, value in payload.model_dump(exclude_none=True).items():
            setattr(post, field, value)
        await post.save()
        return PostResponse.model_validate(post)

    @route.delete("/{post_id}", summary="Delete own post")
    async def destroy(self, post_id: int, user: CurrentUser) -> dict:
        post = await Post.get_or_none(id=post_id, author_id=int(user.id))
        if not post:
            raise HTTPException(404, "Post not found or not yours")
        await post.delete()
        return {"detail": "deleted"}
"""

# ══════════════════════════════════════════════════════════════════════════════
# Telegram
# ══════════════════════════════════════════════════════════════════════════════

_MODEL_USER_TELEGRAM = """\
from tortoise import fields
from tortoise.models import Model


class User(Model):
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

_SCHEMA_USER_TELEGRAM = """\
from pydantic import BaseModel
from forgeapi import BaseSchema


class UserResponse(BaseSchema):
    telegram_id: int
    username:    str | None
    first_name:  str | None
    last_name:   str | None
    is_active:   bool


class UserListResponse(BaseModel):
    items: list[UserResponse]
    total: int
"""

_EVENT_USER_FIRST_LOGIN = """\
from forgeapi import Event


class UserFirstLoginEvent(Event):
    background = True

    def __init__(self, user_id: int, telegram_id: int, username: str | None) -> None:
        self.user_id     = user_id
        self.telegram_id = telegram_id
        self.username    = username
"""

_EVENTS_INIT_TELEGRAM = """\
from .user_first_login_event import UserFirstLoginEvent
from .post_created_event import PostCreatedEvent
"""

_LISTENER_USER_TELEGRAM = """\
import logging
from forgeapi import listen
from app.events.user_first_login_event import UserFirstLoginEvent

logger = logging.getLogger("app")


@listen(UserFirstLoginEvent)
async def on_first_login(event: UserFirstLoginEvent) -> None:
    logger.info("[event] UserFirstLogin  id=%d  telegram_id=%d  username=%s",
                event.user_id, event.telegram_id, event.username)
"""

_CONTROLLER_USER_TELEGRAM = """\
from fastapi import HTTPException
from forgeapi.auth import CurrentUser
from forgeapi.pagination import Pagination
from .controller import Controller, route
from database.models import User
from app.schemas.response.user import UserResponse, UserListResponse
from app.events.user_first_login_event import UserFirstLoginEvent


class UserController(Controller):
    prefix = "/users"
    tags   = ["users"]

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

    @route.get("/", response_model=UserListResponse, summary="List users with pagination")
    async def index(self, pagination: Pagination) -> UserListResponse:
        total = await User.all().count()
        users = await User.all().offset(pagination.offset).limit(pagination.limit)
        return UserListResponse(items=[UserResponse.model_validate(u) for u in users], total=total)
"""

_CONTROLLER_POST_TELEGRAM = """\
from fastapi import HTTPException
from forgeapi.auth import CurrentUser
from forgeapi.pagination import Pagination
from .controller import Controller, route
from database.models import Post, User
from app.schemas.response.post import PostResponse, PostListResponse
from app.schemas.payload.post import PostCreatePayload, PostUpdatePayload
from app.events.post_created_event import PostCreatedEvent


async def _resolve_author(user: CurrentUser) -> int:
    author = await User.get_or_none(telegram_id=int(user.id))
    if not author:
        raise HTTPException(401, "Call GET /api/v1/users/me first to register your account")
    return author.id


class PostController(Controller):
    prefix = "/posts"
    tags   = ["posts"]

    @route.get("/", response_model=PostListResponse, summary="List published posts")
    async def index(self, pagination: Pagination) -> PostListResponse:
        total = await Post.filter(is_published=True).count()
        posts = await Post.filter(is_published=True).offset(pagination.offset).limit(pagination.limit)
        return PostListResponse(items=[PostResponse.model_validate(p) for p in posts], total=total)

    @route.post("/", response_model=PostResponse, summary="Create post (Telegram auth)")
    async def create(self, payload: PostCreatePayload, user: CurrentUser) -> PostResponse:
        author_id = await _resolve_author(user)
        post = await Post.create(
            title=payload.title,
            body=payload.body,
            is_published=payload.is_published,
            author_id=author_id,
        )
        await PostCreatedEvent(post_id=post.id, title=post.title, author_id=author_id).dispatch()
        return PostResponse.model_validate(post)

    @route.get("/{post_id}", response_model=PostResponse, summary="Get post by id")
    async def show(self, post_id: int) -> PostResponse:
        post = await Post.get_or_none(id=post_id, is_published=True)
        if not post:
            raise HTTPException(404, "Post not found")
        return PostResponse.model_validate(post)

    @route.patch("/{post_id}", response_model=PostResponse, summary="Update own post")
    async def update(self, post_id: int, payload: PostUpdatePayload, user: CurrentUser) -> PostResponse:
        author_id = await _resolve_author(user)
        post = await Post.get_or_none(id=post_id, author_id=author_id)
        if not post:
            raise HTTPException(404, "Post not found or not yours")
        for field, value in payload.model_dump(exclude_none=True).items():
            setattr(post, field, value)
        await post.save()
        return PostResponse.model_validate(post)

    @route.delete("/{post_id}", summary="Delete own post")
    async def destroy(self, post_id: int, user: CurrentUser) -> dict:
        author_id = await _resolve_author(user)
        post = await Post.get_or_none(id=post_id, author_id=author_id)
        if not post:
            raise HTTPException(404, "Post not found or not yours")
        await post.delete()
        return {"detail": "deleted"}
"""

# ══════════════════════════════════════════════════════════════════════════════
# Seeders
# ══════════════════════════════════════════════════════════════════════════════

_SEEDER_USER_PASSWORD = """\
from forgeapi.database import Seeder
from database.models import User
from app.utils import hash_password


class UserSeeder(Seeder):
    async def run(self) -> None:
        await User.get_or_create(
            username="admin",
            defaults={
                "email":         "admin@example.com",
                "password_hash": hash_password("admin123"),
                "is_active":     True,
            },
        )
"""

_SEEDER_USER_TELEGRAM = """\
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

_SEEDER_POST = """\
from forgeapi.database import Seeder
from database.models import Post, User


class PostSeeder(Seeder):
    async def run(self) -> None:
        user = await User.first()
        if not user:
            return
        await Post.get_or_create(
            title="Hello World",
            defaults={
                "body":         "This is the first post.",
                "is_published": True,
                "author_id":    user.id,
            },
        )
"""

# ══════════════════════════════════════════════════════════════════════════════
# Entry point
# ══════════════════════════════════════════════════════════════════════════════

def run(root: Path, strategy: str) -> None:
    is_telegram = strategy == "telegram"

    # ── Shared ────────────────────────────────────────────────────────────────
    _write(root / "database/models/__init__.py",         _MODELS_INIT)
    _write(root / "database/models/post.py",             _MODEL_POST)
    _write(root / "app/schemas/response/__init__.py",    "")
    _write(root / "app/schemas/payload/__init__.py",     "")
    _write(root / "app/schemas/response/post.py",        _SCHEMA_POST_RESPONSE)
    _write(root / "app/schemas/payload/post.py",         _SCHEMA_POST_PAYLOAD)
    _write(root / "app/events/post_created_event.py",    _EVENT_POST_CREATED)
    _write(root / "app/listeners/post_listener.py",      _LISTENER_POST)
    _write(root / "database/seeds/post_seeder.py",       _SEEDER_POST)

    if is_telegram:
        _write(root / "database/models/user.py",                     _MODEL_USER_TELEGRAM)
        _write(root / "app/schemas/response/user.py",                _SCHEMA_USER_TELEGRAM)
        _write(root / "app/events/user_first_login_event.py",        _EVENT_USER_FIRST_LOGIN)
        _write(root / "app/events/__init__.py",                      _EVENTS_INIT_TELEGRAM)
        _write(root / "app/listeners/user_listener.py",              _LISTENER_USER_TELEGRAM)
        _write(root / "app/controllers/user_controller.py",          _CONTROLLER_USER_TELEGRAM)
        _write(root / "app/controllers/post_controller.py",          _CONTROLLER_POST_TELEGRAM)
        _write(root / "database/seeds/user_seeder.py",               _SEEDER_USER_TELEGRAM)
    else:
        _write(root / "database/models/user.py",                     _MODEL_USER_PASSWORD)
        _write(root / "app/utils.py",                                _UTILS_PASSWORD)
        _write(root / "app/schemas/user.py",                         _SCHEMA_USER_PASSWORD)
        _write(root / "app/events/user_registered_event.py",         _EVENT_USER_REGISTERED)
        _write(root / "app/events/__init__.py",                      _EVENTS_INIT_PASSWORD)
        _write(root / "app/listeners/user_listener.py",              _LISTENER_USER_PASSWORD)
        _write(root / "app/controllers/post_controller.py",          _CONTROLLER_POST_STD)
        _write(root / "database/seeds/user_seeder.py",               _SEEDER_USER_PASSWORD)
        if strategy == "jwt":
            _write(root / "app/controllers/user_controller.py",      _CONTROLLER_USER_JWT)
        else:
            _write(root / "app/controllers/user_controller.py",      _CONTROLLER_USER_COOKIE)

    _print_summary(root, strategy)


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _print_summary(root: Path, strategy: str) -> None:
    import typer

    n = root.name
    typer.echo("")
    typer.echo(f"  Welcome project ready  (strategy: {strategy})")
    typer.echo("")
    typer.echo("  Run:")
    typer.echo(f"    cd {n}")
    typer.echo("    forgeapi db:init && forgeapi db:makemigrations && forgeapi db:migrate")
    typer.echo("    forgeapi runserver --reload")
    typer.echo("")
    typer.echo("  Endpoints:")

    if strategy == "telegram":
        typer.echo("    GET    /api/v1/users/me         — auto-register + current user  (X-Telegram-Init-Data header)")
    else:
        typer.echo("    POST   /api/v1/users/register   — register")
        typer.echo("    POST   /api/v1/users/login      — login" + (" → JWT token" if strategy == "jwt" else " → sets cookie"))
        if strategy == "cookie":
            typer.echo("    POST   /api/v1/users/logout    — logout (clears cookie)")
        typer.echo("    GET    /api/v1/users/me         — current user (auth required)")

    typer.echo("    GET    /api/v1/users/          — list users (pagination)")
    typer.echo("    POST   /api/v1/posts/          — create post (auth required)")
    typer.echo("    GET    /api/v1/posts/          — list posts (pagination)")
    typer.echo("    GET    /api/v1/posts/{id}      — get post")
    typer.echo("    PATCH  /api/v1/posts/{id}      — update own post")
    typer.echo("    DELETE /api/v1/posts/{id}      — delete own post")
