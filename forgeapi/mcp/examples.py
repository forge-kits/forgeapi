from __future__ import annotations

_EXAMPLES: dict[str, str] = {

"crud_controller": '''\
# Complete CRUD controller with ModelMixin and schema class var

# database/models/post.py
from tortoise import fields, Model
from forgeapi import ModelMixin

class Post(ModelMixin, Model):
    id           = fields.IntField(pk=True)
    title        = fields.CharField(max_length=255)
    body         = fields.TextField()
    author_id    = fields.IntField()
    created_at   = fields.DatetimeField(auto_now_add=True)
    updated_at   = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "posts"

    @classmethod
    def published(cls):
        return cls.filter(is_published=True)


# app/schemas/post.py
from forgeapi import BaseSchema, BaseCreateSchema, BaseUpdateSchema

class PostResponse(BaseSchema):
    title: str
    body: str
    author_id: int

class PostCreatePayload(BaseCreateSchema):
    title: str
    body: str

class PostUpdatePayload(BaseUpdateSchema):
    title: str | None = None
    body: str | None = None


# app/controllers/post_controller.py
from fastapi import Request
from forgeapi.controllers import Controller, route
from forgeapi.auth import CurrentUser
from database.models.post import Post
from app.schemas.post import PostResponse, PostCreatePayload, PostUpdatePayload


class PostController(Controller):
    prefix = "/posts"
    tags   = ["posts"]
    schema = PostResponse      # auto response_model on all routes except 204

    @route.get("/", response_model=None)
    async def index(self, request: Request):
        return await Post.all().order_by("-created_at").paginate(request, PostResponse)

    @route.post("/", status_code=201)
    async def create(self, payload: PostCreatePayload, user: CurrentUser):
        return await Post.create_from(payload, author_id=int(user.id))

    @route.get("/{id}")
    async def show(self, id: int):
        return await Post.find_or_fail(id)

    @route.patch("/{id}")
    async def update(self, id: int, payload: PostUpdatePayload, user: CurrentUser):
        post = await Post.find_or_fail(id)
        return await post.update_from(payload)

    @route.delete("/{id}", status_code=204)
    async def destroy(self, id: int):
        post = await Post.find_or_fail(id)
        await post.delete()
''',

"broadcasting_pubsub": '''\
# BroadcastManager — pub/sub mode (fire-and-forget, fan-out to all running workers)

# app/events/__init__.py
from forgeapi import BroadcastManager

broadcast = BroadcastManager(
    driver="redis",
    url="redis://localhost:6379",
    namespace="myapp",
    mode="pubsub",   # all connected workers receive every message
)


# app/listeners/order_listener.py
from app.events import broadcast

@broadcast.on("order:shipped")
async def send_confirmation(data: dict) -> None:
    await email_service.send(data["email"], f"Order {data['order_id']} shipped!")


# main.py
import app.listeners  # noqa: F401 — registers @broadcast.on handlers
from contextlib import asynccontextmanager
from fastapi import FastAPI
from forgeapi import Core
from app.events import broadcast

@asynccontextmanager
async def lifespan(app):
    await broadcast.connect()
    yield
    await broadcast.disconnect()

app = FastAPI(lifespan=lifespan)
Core(app)

# Emit from a controller:
await broadcast.emit("order:shipped", {"order_id": 42, "email": "alice@example.com"})
''',

"broadcasting_stream": '''\
# BroadcastManager — stream mode (persistent, messages survive worker restart)

# app/events/__init__.py
from forgeapi import BroadcastManager

broadcast = BroadcastManager(
    driver="redis",
    url="redis://localhost:6379",
    namespace="myapp",
    mode="stream",   # persistent: messages survive restarts, maxlen caps storage
    maxlen=1000,
)


# app/listeners/order_listener.py
from app.events import broadcast

@broadcast.on("order:created")
async def handle_order(data: dict) -> None:
    await warehouse.fulfill(data["order_id"])


# main.py
import app.listeners  # noqa: F401 — registers @broadcast.on handlers
from contextlib import asynccontextmanager
from fastapi import FastAPI
from forgeapi import Core
from app.events import broadcast

@asynccontextmanager
async def lifespan(app):
    await broadcast.connect(group="backend", consumer="worker-1")
    yield
    await broadcast.disconnect()

app = FastAPI(lifespan=lifespan)
Core(app)

# Emit from a controller:
await broadcast.emit("order:created", {"order_id": 42, "total": 99.9})


# Second service consumer (worker-2 in same group = load balancing):
import asyncio
from forgeapi import BroadcastManager

broadcast2 = BroadcastManager(driver="redis", url="redis://localhost:6379",
                               namespace="myapp", mode="stream")

@broadcast2.on("order:created")
async def handle(data: dict) -> None:
    print(f"[worker-2] {data}")

async def main():
    await broadcast2.connect(group="backend", consumer="worker-2")
    try:
        await asyncio.sleep(float("inf"))
    finally:
        await broadcast2.disconnect()

asyncio.run(main())
''',

"jwt_auth": '''\
# JWT auth — login, refresh, protected route

# database/models/user.py
import hashlib
from tortoise import fields, Model
from forgeapi import ModelMixin

class User(ModelMixin, Model):
    id         = fields.IntField(pk=True)
    email      = fields.CharField(max_length=255, unique=True)
    password   = fields.CharField(max_length=255)
    username   = fields.CharField(max_length=100)
    is_active  = fields.BooleanField(default=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "users"

    def set_password(self, raw: str) -> None:
        self.password = hashlib.sha256(raw.encode()).hexdigest()

    def verify_password(self, raw: str) -> bool:
        return self.password == hashlib.sha256(raw.encode()).hexdigest()


# app/controllers/auth_controller.py
from fastapi import HTTPException
from forgeapi.controllers import Controller, route
from forgeapi.auth import CurrentUser, auth
from forgeapi.exceptions import TokenExpiredError, TokenInvalidError
from database.models.user import User


class AuthController(Controller):
    prefix = "/auth"
    tags   = ["auth"]

    @route.post("/register", status_code=201)
    async def register(self, payload: RegisterPayload) -> dict:
        if await User.filter(email=payload.email).exists():
            raise HTTPException(422, "Email already registered")
        user = User(email=payload.email, username=payload.username)
        user.set_password(payload.password)
        await user.save()
        access  = auth.token(user)
        refresh = auth.refresh_token(user)
        return {"access_token": access, "refresh_token": refresh, "token_type": "bearer"}

    @route.post("/login")
    async def login(self, payload: LoginPayload) -> dict:
        user = await User.get_or_none(email=payload.email)
        if not user or not user.verify_password(payload.password):
            raise HTTPException(401, "Invalid credentials")
        if not user.is_active:
            raise HTTPException(403, "Account disabled")
        access  = auth.token(user)
        refresh = auth.refresh_token(user)
        return {"access_token": access, "refresh_token": refresh, "token_type": "bearer"}

    @route.post("/refresh")
    async def refresh(self, payload: RefreshPayload) -> dict:
        try:
            data = auth.decode(payload.refresh_token, expected_type="refresh")
        except TokenExpiredError:
            raise HTTPException(401, "Refresh token expired")
        except TokenInvalidError:
            raise HTTPException(401, "Invalid refresh token")
        user = await User.find_or_fail(int(data["sub"]))
        return {"access_token": auth.token(user), "token_type": "bearer"}

    @route.get("/me")
    async def me(self, user: CurrentUser) -> dict:
        db_user = await User.find_or_fail(int(user.id))
        return {"id": db_user.id, "email": db_user.email, "username": db_user.username}
''',

"rbac": '''\
# Full RBAC — model, seeder, protected routes

# database/models/user.py
from tortoise import fields
from forgeapi import ModelMixin
from forgeapi.permissions import PermissionsMixin
from tortoise import Model

class User(ModelMixin, PermissionsMixin, Model):
    id        = fields.IntField(pk=True)
    email     = fields.CharField(max_length=255, unique=True)
    username  = fields.CharField(max_length=100)
    is_active = fields.BooleanField(default=True)

    class Meta:
        table = "users"


# app/controllers/post_controller.py
from forgeapi.controllers import Controller, route
from forgeapi.auth import CurrentUser
from forgeapi.permissions import require_permission, require_role

class PostController(Controller):
    prefix = "/posts"
    tags   = ["posts"]

    @route.get("/")
    async def index(self) -> dict:
        return {"posts": []}

    @route.post("/", status_code=201)
    async def create(self, payload: PostCreatePayload, user=require_permission("create:posts")):
        return await Post.create_from(payload, author_id=user.id)

    @route.delete("/{id}", status_code=204)
    async def destroy(self, id: int, user=require_permission("delete:posts", "admin:panel")):
        post = await Post.find_or_fail(id)
        await post.delete()

    @route.get("/admin/stats")
    async def admin_stats(self, user=require_role("admin")) -> dict:
        return {"total_posts": await Post.all().count()}

    @route.patch("/{id}")
    async def update(self, id: int, payload: PostUpdatePayload, user: CurrentUser):
        db_user = await User.find_or_fail(int(user.id))
        if not await db_user.can("edit:posts"):
            raise HTTPException(403, "Forbidden")
        post = await Post.find_or_fail(id)
        return await post.update_from(payload)
''',

"pagination": '''\
# Pagination — QuerySet .paginate() (recommended)

from fastapi import Request
from forgeapi.controllers import Controller, route
from database.models.product import Product
from app.schemas.product import ProductResponse


class ProductController(Controller):
    prefix = "/products"
    tags   = ["products"]
    schema = ProductResponse

    @route.get("/", response_model=None)
    async def index(self, request: Request):
        # ?page=1&per_page=20 (default)
        return await Product.all().order_by("-created_at").paginate(request, ProductResponse)

    @route.get("/search", response_model=None)
    async def search(self, request: Request, q: str):
        return await Product.filter(name__icontains=q).paginate(request, ProductResponse)

# Response shape:
# {
#   "data": [...],
#   "meta": {"current_page": 1, "per_page": 20, "total": 100, "last_page": 5, "from": 1, "to": 20},
#   "links": {"prev": null, "next": "http://...?page=2&per_page=20"}
# }
''',

"guard": '''\
# Guards — API key guard, active-user guard, admin guard

# app/guards/api_key_guard.py
from fastapi import HTTPException, Request
from forgeapi.middleware import Guard

class ApiKeyGuard(Guard):
    def __init__(self, header: str = "X-API-Key"):
        self.header = header

    async def handle(self, request: Request) -> None:
        if not request.headers.get(self.header):
            raise HTTPException(403, "Invalid or missing API key")


# app/guards/active_user_guard.py
from fastapi import HTTPException
from forgeapi.middleware import Guard
from forgeapi.auth import CurrentUser

class ActiveUserGuard(Guard):
    async def handle(self, user: CurrentUser) -> None:
        if not getattr(user, "is_active", True):
            raise HTTPException(403, "Account is disabled")


# Per-route:
from fastapi import Depends

@route.post("/stripe", dependencies=[Depends(ApiKeyGuard(header="X-Stripe-Signature"))])
async def stripe(self, payload: dict) -> dict:
    return {"received": True}

# Per-controller (every route protected):
class AdminController(Controller):
    prefix = "/admin"
    tags   = ["admin"]
    guards = [ActiveUserGuard()]
''',

"cache": '''\
# Cache — common patterns

from forgeapi import Cache
from database.models.post import Post
from app.schemas.post import PostResponse


# Simple get/set
async def get_settings():
    settings = await Cache.get("app:settings")
    if settings is None:
        settings = await load_settings_from_db()
        await Cache.set("app:settings", settings, ttl=3600)
    return settings


# remember() — get or compute
async def get_popular_posts():
    return await Cache.remember(
        "posts:popular",
        fn=lambda: Post.filter(is_published=True).order_by("-views").limit(10),
        ttl=300,
    )


# pull() — one-time token (get and delete)
async def verify_reset_token(user_id: int, token: str) -> bool:
    stored = await Cache.pull(f"reset:token:{user_id}")
    return stored == token


# Counters
async def track_view(post_id: int) -> int:
    return await Cache.increment(f"views:post:{post_id}")


# Controller example
class PostController(Controller):
    prefix = "/posts"
    tags   = ["posts"]

    @route.get("/popular", response_model=None)
    async def popular(self, request: Request):
        cached = await Cache.get("posts:popular")
        if cached:
            return cached
        result = await Post.filter(is_published=True).order_by("-views").paginate(request, PostResponse)
        await Cache.set("posts:popular", result, ttl=60)
        return result
''',

}


def get_example(pattern: str) -> str:
    """Return a complete working code example for a forge-kits pattern.

    Patterns: crud_controller, redis_event, stream_event, jwt_auth, rbac,
              pagination, guard, cache

    Args:
        pattern: One of the pattern names listed above (case-insensitive,
                 underscores or hyphens accepted).

    Returns:
        Complete, copy-pasteable Python code implementing the pattern.
    """
    key = pattern.lower().strip().replace("-", "_")
    example = _EXAMPLES.get(key)
    if example:
        return example
    available = ", ".join(sorted(_EXAMPLES.keys()))
    return (
        f"Unknown pattern '{pattern}'. Available patterns: {available}\n\n"
        "Each pattern returns a complete, runnable code example."
    )
