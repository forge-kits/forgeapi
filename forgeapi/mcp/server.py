"""forge-kits MCP Server.

Start via:
    forgeapi-mcp

Or register in .claude/settings.json:
    {
      "mcpServers": {
        "forge-kits": {
          "command": "forgeapi-mcp"
        }
      }
    }
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("forge-kits")

# ---------------------------------------------------------------------------
# Topic docs database
# ---------------------------------------------------------------------------

_DOCS: dict[str, str] = {

"core": """\
# forge-kits: Core (entry-point wiring)

Import: `from forgeapi import Core`

## Constructor signature
```python
Core(
    app: FastAPI,
    *,
    auth: bool | str = False,        # False | True | "jwt" | "cookie" | "telegram"
    cors: bool | list[str] = False,  # False | True | ["https://example.com"]
    rate_limit: bool | int = False,  # False | True (=60) | int (req/min)
    pagination: bool | int = False,  # False | True | int (default_limit)
    request_id: bool = False,        # inject X-Request-ID header
    events: bool = False,            # auto-load listeners from listeners_dir
    access_log: bool = True,         # log every request
    controllers: bool = True,        # auto-discover *_controller.py
    permissions: bool | type | None = None,  # True=auto-detect, or pass User model
    middleware: list | None = None,  # [(MiddlewareClass, {kwargs}), ...]
    debug: bool = False,             # Telescope UI at /_forge/telescope/requests
    config_path: str = "forgeapi.toml",
)
```

## Full main.py pattern
```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from forgeapi import Core
from tortoise.contrib.fastapi import register_tortoise
from app.config import TORTOISE_ORM

@asynccontextmanager
async def lifespan(app):
    yield

app = FastAPI(lifespan=lifespan)

core = Core(
    app,
    auth="jwt",
    cors=["*"],
    rate_limit=60,
    pagination=20,
    request_id=True,
    events=True,
    permissions=True,
)

register_tortoise(
    app,
    config=TORTOISE_ORM,
    generate_schemas=False,
    add_exception_handlers=True,
)
```

## Notes
- `controllers=True` is the default; auto-discovers every `*_controller.py` in
  `structure.controllers_dir` (recursive). Routes are prefixed with `base_prefix`.
- `auth=True` reads `strategy` from forgeapi.toml `[auth]` section.
- `permissions=True` scans `models_dir` for the first `PermissionsMixin` subclass.
  Use `permissions=User` to pass the model explicitly.
- `Core.use(MiddlewareClass, **kwargs)` adds middleware after construction.
- `Core.include_router(router, prefix="")` prepends `base_prefix`.
- `core.auth` — the `AuthBackend` instance, or `None`.
- `core.config` — the loaded `KitConfig`.
""",

"controllers": """\
# forge-kits: Controllers

Imports:
```python
from forgeapi.controllers import Controller, route
from forgeapi.auth import CurrentUser, OptionalUser
from forgeapi.pagination import Pagination
from fastapi import HTTPException, Depends
```

## Class structure
```python
class PostController(Controller):
    prefix = "/posts"          # auto-derived if omitted (see auto-prefix rules)
    tags   = ["posts"]         # auto-derived from prefix if omitted
    guards = [SomeGuard()]     # applied to EVERY route in this controller
```

## Auto-prefix derivation rules
- `PostController`              → `/posts`
- `AdminUserController`         → `/admin/users`
- `SuperAdminUserController`    → `/super/admin/users`
- `ApiV1ArticleController`      → `/api/v1/articles`
- Logic: split CamelCase words, last word = resource (pluralised),
  preceding words = namespace path segments.
- Pluralisation: `y` → `ies`; already ending in `s` → unchanged; else append `s`.

## Route decorators
```python
@route.get("/")
@route.post("/", status_code=201)
@route.put("/{id}")
@route.patch("/{id}")
@route.delete("/{id}", status_code=204)
# Also: @route("/path", methods=["GET", "POST"])
# Extra kwargs are forwarded to FastAPI add_api_route (response_model, etc.)
```

## Dependency injection
- `user: CurrentUser`  — raises HTTP 401 if not authenticated
- `user: OptionalUser` — returns `None` if not authenticated
- `pagination: Pagination` — `?page` and `?limit` query params
- `payload: SomeSchema` — request body (Pydantic model)
- Path params declared in path string, typed as method args
- `dependencies=[Depends(SomeGuard())]` — per-route guard

## AuthUser fields (from CurrentUser / OptionalUser)
- `user.id: str` — from JWT `sub` claim (cast to int when used as DB FK)
- `user.username: str | None`
- `user.extra: dict` — all non-reserved JWT claims
- `user.auth_method: str` — "jwt" | "cookie" | "telegram"

## Full CRUD example
```python
class PostController(Controller):
    prefix = "/posts"
    tags   = ["posts"]

    @route.get("/")
    async def index(self, pagination: Pagination) -> dict:
        total = await Post.all().count()
        items = await Post.all().offset(pagination.offset).limit(pagination.limit)
        return {"items": items, "total": total, "page": pagination.page}

    @route.post("/", status_code=201)
    async def create(self, payload: PostCreate, user: CurrentUser) -> dict:
        post = await Post.create(**payload.model_dump(), author_id=int(user.id))
        return {"id": post.id, "title": post.title}

    @route.get("/{post_id}")
    async def show(self, post_id: int) -> dict:
        post = await Post.get_or_none(id=post_id)
        if not post:
            raise HTTPException(404, "Not found")
        return {"id": post.id}

    @route.patch("/{post_id}")
    async def update(self, post_id: int, payload: PostUpdate, user: CurrentUser) -> dict:
        post = await Post.get_or_none(id=post_id, author_id=int(user.id))
        if not post:
            raise HTTPException(404)
        await post.update_from_dict(payload.model_dump(exclude_none=True)).save()
        return {"id": post.id}

    @route.delete("/{post_id}", status_code=204)
    async def destroy(self, post_id: int, user: CurrentUser):
        deleted = await Post.filter(id=post_id, author_id=int(user.id)).delete()
        if not deleted:
            raise HTTPException(404)
```

## Important rules
- Each request gets a **fresh** controller instance (no shared state across requests).
- Guards in `guards = [...]` are wrapped in `Depends()` automatically.
- The controller file must be named `*_controller.py` for auto-discovery to work.
- Do NOT put `__init__` on the controller class unless you add `super().__init__()`.
""",

"events": """\
# forge-kits: Events & EventBus

## Base Event class
```python
from forgeapi import Event

class MyEvent(Event):
    background: ClassVar[bool] = False    # True = asyncio.create_task (fire-and-forget)
    redis: ClassVar[bool] = False         # True = publish to Redis
    redis_type: ClassVar[str] = "pubsub" # "pubsub" | "stream"
    namespace: ClassVar[str] = "forgeapi:events"  # stream key prefix
    ttl: ClassVar[int | None] = None     # dedup window in seconds (pubsub only)

    def __init__(self, field1: int, field2: str) -> None:
        self.field1 = field1
        self.field2 = field2
```

Every instance automatically gets `event.event_id` (UUID4).

## Listener via decorator
```python
from forgeapi import listen

@listen(MyEvent)
async def handle_my_event(event: MyEvent) -> None:
    # listeners MUST be async def
    await do_something(event.field1)
```

## Dispatch
```python
await MyEvent(field1=1, field2="hello").dispatch()
```

## Local background event
```python
class UserLoggedIn(Event):
    background = True
    def __init__(self, user_id: int) -> None:
        self.user_id = user_id
```

## Redis pub/sub (fan-out across workers)
```python
class OrderShipped(Event):
    background = True
    redis = True
    redis_type = "pubsub"
    ttl = 300  # only one worker processes per event_id within 5 min

    def __init__(self, order_id: int) -> None:
        self.order_id = order_id
```
Lifespan setup for pub/sub:
```python
import asyncio
from forgeapi import EventBus

@asynccontextmanager
async def lifespan(app):
    bus = EventBus.get_instance()
    await bus.redis_connect("redis://localhost:6379")
    task = asyncio.create_task(bus.start_redis_subscriber())
    yield
    task.cancel()
    await bus.redis_disconnect()
```

## Redis Streams (persistent, consumer groups)
```python
class OrderEvent(Event):
    background = True
    redis = True
    redis_type = "stream"
    namespace = "shop"  # stream key = "shop:OrderEvent"

    def __init__(self, order_id: int, total: float) -> None:
        self.order_id = order_id
        self.total = total
```
Consumer worker:
```python
bus = EventBus.get_instance()
await bus.redis_connect("redis://localhost:6379")

@bus.on(OrderEvent)
async def handle_order(event: OrderEvent) -> None:
    await process(event.order_id)

await bus.start_stream_subscriber(
    group="warehouse_group",
    consumer="worker_1",
    event_classes=[OrderEvent],
)
```

## RedisBus (cross-project, no shared Python classes)
```python
from forgeapi import RedisBus

bus = RedisBus("redis://localhost:6379", namespace="shop")

@bus.on("order:created")
async def handle(data: dict) -> None:
    await notify(data["id"])

await bus.emit("order:created", {"id": 1, "total": 99.0})
```

## EventBus API (rarely needed directly)
- `EventBus.get_instance()` — singleton
- `EventBus.reset()` — clear all listeners (use in tests)
- `bus.register(EventClass, listener_fn)` — manual registration
- `bus.on(EventClass)` — decorator registration
- `bus.load_from_dir("app/listeners")` — import all listener files
- `bus.set_redis(client)` — attach redis.asyncio client
- `bus.redis_connect(url)` — create + attach client from URL
- `bus.redis_disconnect()` — close connection
- `bus.start_redis_subscriber()` — coroutine, run as background task
- `bus.start_stream_subscriber(group, consumer, event_classes)` — coroutine
- `bus.drain(timeout=30.0)` — await all pending background tasks

## Decision guide
- Local listeners: `redis=False` (default)
- Same-codebase multi-worker fan-out: `redis=True, redis_type="pubsub"`
- Cross-service or survives restart: `redis=True, redis_type="stream"`
- Cross-project no shared code: `RedisBus`

## Testing
```python
import pytest
from forgeapi import EventBus

@pytest.fixture(autouse=True)
def reset_bus():
    EventBus.reset()
    yield
    EventBus.reset()
```
""",

"auth": """\
# forge-kits: Authentication

## Quick setup via Core
```python
Core(app, auth="jwt")       # reads JWT_SECRET env var, 30min access TTL
Core(app, auth="cookie")    # cookie-based session
Core(app, auth="telegram")  # Telegram mini-app auth (BOT_TOKEN env var)
```

## Manual setup
```python
from forgeapi.auth import AuthBackend, JWTStrategy, set_global_backend

strategy = JWTStrategy(
    secret_key="s3cr3t",
    algorithm="HS256",        # HS256 | HS384 | HS512
    access_token_expire_minutes=30,
    refresh_token_expire_days=7,
)
auth = AuthBackend(strategy=strategy)
set_global_backend(auth)
```

## Using in routes
```python
from forgeapi.auth import CurrentUser, OptionalUser

@route.get("/me")
async def me(self, user: CurrentUser) -> dict:
    return {"id": user.id, "username": user.username}

@route.get("/feed")
async def feed(self, user: OptionalUser) -> dict:
    if user:
        return personalised_feed(int(user.id))
    return public_feed()
```

## AuthUser fields
- `user.id: str` — JWT `sub` claim; use `int(user.id)` for DB queries
- `user.username: str | None`
- `user.extra: dict` — any non-standard JWT claims
- `user.auth_method: str` — "jwt" | "cookie" | "telegram"

## Token operations
```python
from forgeapi.auth import auth   # proxy to active strategy

# Issue tokens (JWT strategy)
access  = auth.create_access_token({"sub": str(user.id), "username": user.username})
refresh = auth.create_refresh_token({"sub": str(user.id)})

# Decode manually
payload = auth.decode(token, expected_type="access")  # raises TokenExpiredError | TokenInvalidError

# Cookie strategy
auth.set_cookie(response, {"sub": str(user.id)})
auth.delete_cookie(response)
```

## Login / Register endpoint pattern (JWT)
```python
from fastapi import HTTPException
from forgeapi.auth import auth
from forgeapi.exceptions import TokenExpiredError, TokenInvalidError

@route.post("/login", status_code=200)
async def login(self, payload: LoginPayload) -> dict:
    user = await User.get_or_none(email=payload.email)
    if not user or not user.verify_password(payload.password):
        raise HTTPException(401, "Invalid credentials")
    access  = auth.create_access_token({"sub": str(user.id), "username": user.username})
    refresh = auth.create_refresh_token({"sub": str(user.id)})
    return {"access_token": access, "refresh_token": refresh, "token_type": "bearer"}

@route.post("/refresh")
async def refresh(self, payload: RefreshPayload) -> dict:
    try:
        data = auth.decode(payload.refresh_token, expected_type="refresh")
    except (TokenExpiredError, TokenInvalidError) as e:
        raise HTTPException(401, str(e))
    access = auth.create_access_token({"sub": data["sub"]})
    return {"access_token": access, "token_type": "bearer"}
```

## Exceptions
- `forgeapi.exceptions.TokenExpiredError` — token expired
- `forgeapi.exceptions.TokenInvalidError` — bad signature or wrong type
- `forgeapi.exceptions.ForgeAPIConfigError` — misconfiguration

## JWTStrategy token claims
- `sub` — user identifier
- `exp` — expiry (auto-added)
- `type` — "access" | "refresh" (auto-added)
- `iat` — issued at (if set externally)
- All other keys end up in `user.extra`
""",

"permissions": """\
# forge-kits: Permissions (Spatie-style RBAC)

## Model setup
```python
from forgeapi.permissions import PermissionsMixin
from tortoise import fields

class User(PermissionsMixin):
    id        = fields.IntField(primary_key=True)
    email     = fields.CharField(max_length=255, unique=True)
    is_active = fields.BooleanField(default=True)

    class Meta:
        table = "users"
```

Add `"forgeapi.permissions.models"` to your Tortoise `apps` config, then run migrations.

## Core(app, permissions=True) or permissions=User
```python
Core(app, auth="jwt", permissions=True)  # auto-detects PermissionsMixin model
Core(app, auth="jwt", permissions=User)  # explicit
```

## Route-level dependency injection
```python
from forgeapi.permissions import require_permission, require_role

@route.delete("/{id}")
async def destroy(self, id: int, user=require_permission("delete:posts")):
    # user is the DB model instance (not AuthUser)
    ...

@route.get("/admin/stats")
async def stats(self, user=require_role("admin")):
    ...

# OR logic — user must have at least one
@route.post("/")
async def create(self, payload: PostCreate, user=require_permission("create:posts", "admin")):
    ...
```

## Instance-level checks
```python
await user.can("edit:posts")                           # True/False (direct OR via role)
await user.cannot("delete:posts")                      # inverse
await user.has_all_permissions("edit:posts", "publish:posts")  # AND check
await user.has_role("admin")                           # True/False (any of listed)
await user.has_all_roles("admin", "moderator")         # AND check
await user.get_all_permissions()                       # list[str], cached per request
await user.get_role_names()                            # list[str]
```

## Granting / revoking
```python
# Direct permissions
await user.give_permission("edit:posts")               # auto-creates if missing
await user.give_permission("create:posts", "delete:posts")
await user.revoke_permission("delete:posts")

# Roles
await user.assign_role("editor")                       # auto-creates if missing
await user.assign_role("admin", "moderator")
await user.remove_role("editor")
```

## Role model API
```python
from forgeapi.permissions.models import Permission, Role

perm = await Permission.find_or_create("publish:articles")
role = await Role.find_or_create("editor")
await role.give_permission("create:posts", "edit:posts", "publish:articles")
await role.revoke_permission("publish:articles")
await role.has_permission("edit:posts")  # True/False

await user.assign_role("editor")
```

## Class-level filters (QuerySet)
```python
admins     = await (await User.with_role("admin"))
non_admins = await (await User.without_role("admin"))
count      = await (await User.with_role("admin")).count()
```

## Permission naming convention
Use `action:resource` format: `"edit:posts"`, `"delete:comments"`, `"admin:panel"`.
Guard defaults to `"api"` — pass `guard="web"` for web-context checks.

## DB tables created
- `permissions` (id, name, guard)
- `roles` (id, name, guard)
- `role_permissions` (M2M through table)
- `model_has_roles` (model_type, model_id, role_id)
- `model_has_permissions` (model_type, model_id, permission_id)
""",

"pagination": """\
# forge-kits: Pagination

## Import
```python
from forgeapi.pagination import Pagination
# Pagination is an Annotated[Paginator, Depends()] type alias
```

## Usage in a route
```python
@route.get("/")
async def index(self, pagination: Pagination) -> dict:
    total = await Post.all().count()
    items = await Post.all().offset(pagination.offset).limit(pagination.limit)
    return {
        "items": items,
        "total": total,
        "page": pagination.page,
        "limit": pagination.limit,
    }
```

## Paginator attributes
- `pagination.page: int`   — current page, 1-based (from `?page=`)
- `pagination.limit: int`  — items per page, clamped to MAX_LIMIT (from `?limit=`)
- `pagination.offset: int` — `(page - 1) * limit`, use in `.offset()`

## Query string
```
GET /posts?page=2&limit=50
```

## Global configuration
```python
# Via Core (reads forgeapi.toml [pagination] or uses int directly):
Core(app, pagination=20)  # default_limit=20, max_limit from toml

# Via Paginator class directly:
from forgeapi.pagination import Paginator
Paginator.configure(default_limit=10, max_limit=50)
```

## forgeapi.toml
```toml
[pagination]
default_limit = 20
max_limit     = 100
```

## Defaults
- `DEFAULT_LIMIT = 20`
- `MAX_LIMIT = 100`
- `?page` minimum = 1, maximum = 10000
""",

"schemas": """\
# forge-kits: Schemas (Pydantic)

Imports:
```python
from forgeapi import BaseSchema, BaseCreateSchema, BaseUpdateSchema
from pydantic import BaseModel
```

## BaseSchema — response schema
```python
class PostResponse(BaseSchema):
    # Inherits: id (int|str), created_at (datetime), updated_at (datetime)
    # model_config = {"from_attributes": True}  — reads from Tortoise ORM instances
    title: str
    body: str
    author_id: int

# Usage:
response = PostResponse.model_validate(orm_post_instance)
```

## BaseCreateSchema — POST request body
```python
class PostCreate(BaseCreateSchema):
    # Plain BaseModel, all fields required
    title: str
    body: str
    tags: list[str] = []
```

## BaseUpdateSchema — PATCH request body
```python
class PostUpdate(BaseUpdateSchema):
    # ALL fields MUST be Optional[...] = None
    # Raises TypeError at class definition if a required field is declared
    title: str | None = None
    body: str | None = None
```

## Using in a controller
```python
@route.post("/", status_code=201)
async def create(self, payload: PostCreate, user: CurrentUser) -> dict:
    post = await Post.create(**payload.model_dump(), author_id=int(user.id))
    return PostResponse.model_validate(post).model_dump()

@route.patch("/{id}")
async def update(self, id: int, payload: PostUpdate, user: CurrentUser) -> dict:
    post = await Post.get_or_none(id=id, author_id=int(user.id))
    if not post:
        raise HTTPException(404)
    await post.update_from_dict(payload.model_dump(exclude_none=True)).save()
    return PostResponse.model_validate(post).model_dump()
```

## generate:schema CLI (typed from Tortoise model)
```
forgeapi generate:schema Post --payload        # Create, Update, (Read) payloads
forgeapi generate:schema Post --response       # PostResponse + PostListResponse
forgeapi generate:schema Post --payload -crud  # all four payload types
forgeapi generate:schema Post --payload --cu   # Create + Update only
```

Generated payload classes:
- `PostCreatePayload(BaseCreateSchema)` — from `c`
- `PostGetPayload(BaseModel)` — from `r`
- `PostUpdatePayload(BaseUpdateSchema)` — from `u`
- `PostDeletePayload(BaseModel)` — from `d`
- `PostResponse(BaseSchema)` + `PostListResponse(BaseModel)` — from `--response`
""",

"middleware": """\
# forge-kits: Middleware & Guards

## Built-in middleware (enabled via Core)
- `access_log=True` — logs method, path, status code, duration
- `request_id=True` — injects `X-Request-ID` (UUID) into request and response
- `cors=["*"]` — adds CORSMiddleware with given origins
- `rate_limit=60` — IP-based rate limit (requests/minute)

## Custom middleware
```python
from forgeapi.middleware import Middleware
from fastapi import Request
from starlette.responses import Response

class TimingMiddleware(Middleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        import time
        start = time.monotonic()
        response = await call_next(request)
        response.headers["X-Process-Time"] = str(time.monotonic() - start)
        return response

# Register:
Core(app, middleware=[TimingMiddleware])
# Or after Core:
core.use(TimingMiddleware)
core.use(TenantMiddleware, default_tenant="acme")
```

## Guard — per-route / per-controller DI middleware
```python
from forgeapi.middleware import Guard
from fastapi import HTTPException, Request

class ApiKeyGuard(Guard):
    def __init__(self, header: str = "X-API-Key"):
        self.header = header

    async def handle(self, request: Request) -> None:
        if not request.headers.get(self.header):
            raise HTTPException(403, "Missing API key")
```

Per-route:
```python
from fastapi import Depends

@route.delete("/{id}", dependencies=[Depends(ApiKeyGuard())])
async def destroy(self, id: int): ...
```

Per-controller (every route):
```python
class AdminController(Controller):
    guards = [ApiKeyGuard()]
```

Guard with injected dependencies:
```python
from forgeapi.auth import CurrentUser

class ActiveUserGuard(Guard):
    async def handle(self, user: CurrentUser) -> None:
        if not getattr(user, "is_active", True):
            raise HTTPException(403, "Account disabled")
```

## SecurityHeaders middleware
```python
from forgeapi.middleware.security_headers import SecurityHeadersMiddleware
core.use(SecurityHeadersMiddleware)  # adds X-Content-Type-Options, X-Frame-Options, etc.
```
""",

"cli": """\
# forge-kits: CLI Reference

Install: `pip install forge-kits`   (typer-based CLI, no extras needed)
Entry point: `forgeapi`

## Project scaffolding
```
forgeapi init <project-name>
```
Prompts for auth strategy, DB driver, optional boilerplate. Creates:
  project/main.py  forgeapi.toml  .env  pyproject.toml
  app/controllers/  app/events/  app/listeners/  app/schemas/
  database/models/  database/seeds/

## Code generation
```
forgeapi make:controller <Name>   [-m] [-s]      # + optional model/schema
forgeapi make:model <Name>        [-c] [-s]      # + optional controller/schema
forgeapi make:schema <Name>       [-m] [-c]      # stub schemas (3 classes with pass)
forgeapi make:event <Name>                       # Event subclass
forgeapi make:listener <Name>                    # @listen handler file
forgeapi make:seed <Name>                        # Seeder subclass
```

Compound flags: `--ms`, `--mc`, `--mcs`, `-cs`, `-csu` (any permutation of m/c/s).

Namespace controllers (CamelCase word = path segment):
```
forgeapi make:controller AdminUser      → app/controllers/admin/user_controller.py
forgeapi make:controller ApiV1Post      → app/controllers/api/v1/post_controller.py
```

## Typed schema generation (from existing Tortoise model)
```
forgeapi generate:schema Post --payload           # CreatePayload + UpdatePayload
forgeapi generate:schema Post --response          # PostResponse + PostListResponse
forgeapi generate:schema Post --payload -crud     # all four: c/r/u/d payloads
forgeapi generate:schema Post --payload --cu      # Create + Update only
forgeapi generate:schema Post --payload --response
```

## DB commands (requires tortoise-orm extra)
```
forgeapi db:init                 # initialise aerich migration config
forgeapi db:makemigrations [-n <name>]  # generate migration
forgeapi db:migrate              # apply pending migrations
forgeapi db:downgrade            # revert last migration
forgeapi db:history              # show migration log
forgeapi db:seed                 # run all seeders
forgeapi db:seed User Post       # run specific seeders by class name
forgeapi db:fresh                # TRUNCATE all tables (asks confirmation)
forgeapi db:fresh --force        # DROP all tables (irreversible)
```

## Inspection commands
```
forgeapi routers    # list all registered routes (METHOD, PATH, HANDLER)
forgeapi models     # list all Tortoise model classes, tables, and fields
```

## Dev server
```
forgeapi runserver
forgeapi runserver --port 9000 --host 0.0.0.0 --reload
```
""",

"config": """\
# forge-kits: Configuration (forgeapi.toml)

Place `forgeapi.toml` at your project root. All sections are optional.

## Full example
```toml
[project]
name        = "my-api"
version     = "0.1.0"
description = "My FastAPI service"

[structure]
models_dir      = "database/models"
controllers_dir = "app/controllers"
schemas_dir     = "app/schemas"
events_dir      = "app/events"
listeners_dir   = "app/listeners"
seeds_dir       = "database/seeds"
base_prefix     = "/api/v1"

[auth]
strategy           = "jwt"          # "jwt" | "cookie" | "telegram"
jwt_secret_env     = "JWT_SECRET"   # env var name for the secret
access_ttl_minutes = 30
refresh_ttl_days   = 7
cookie_name        = "session"
cookie_httponly    = true
cookie_secure      = true

[pagination]
default_limit = 20
max_limit     = 100

[database]
tortoise_orm = "app.config.TORTOISE_ORM"
```

## Loading in code
```python
from forgeapi import load_config, KitConfig

cfg: KitConfig = load_config()            # reads "forgeapi.toml"
cfg = load_config("path/to/other.toml")   # custom path

# Access:
cfg.project.name               # str
cfg.structure.controllers_dir  # str
cfg.auth.strategy              # str
cfg.pagination.default_limit   # int
```

## BaseAppSettings
```python
from forgeapi import BaseAppSettings

class Settings(BaseAppSettings):
    database_url: str
    redis_url: str | None = None
    jwt_secret: str
    debug: bool = False
    # Reads from .env automatically (pydantic-settings)
    # Sensitive fields (password, secret, key, token) masked in repr

settings = Settings()
```

## Defaults when forgeapi.toml is absent
- `controllers_dir = "app/controllers"`
- `models_dir = "database/models"`
- `base_prefix = "/api/v1"`
- `auth.strategy = "jwt"`
- `pagination.default_limit = 20, max_limit = 100`
""",

}

# ---------------------------------------------------------------------------
# Example patterns database
# ---------------------------------------------------------------------------

_EXAMPLES: dict[str, str] = {

"crud_controller": '''\
# Complete CRUD controller with Tortoise ORM model and Pydantic schemas

# database/models/post.py
from tortoise import fields
from tortoise.models import Model

class Post(Model):
    id         = fields.IntField(primary_key=True)
    title      = fields.CharField(max_length=255)
    body       = fields.TextField()
    author_id  = fields.IntField()
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "posts"


# app/schemas/post.py
from forgeapi import BaseSchema, BaseCreateSchema, BaseUpdateSchema

class PostCreate(BaseCreateSchema):
    title: str
    body: str

class PostUpdate(BaseUpdateSchema):
    title: str | None = None
    body: str | None = None

class PostResponse(BaseSchema):
    title: str
    body: str
    author_id: int


# app/controllers/post_controller.py
from fastapi import HTTPException
from forgeapi.controllers import Controller, route
from forgeapi.auth import CurrentUser, OptionalUser
from forgeapi.pagination import Pagination
from database.models.post import Post
from app.schemas.post import PostCreate, PostUpdate, PostResponse


class PostController(Controller):
    prefix = "/posts"
    tags   = ["posts"]

    @route.get("/")
    async def index(self, pagination: Pagination, user: OptionalUser) -> dict:
        total = await Post.all().count()
        items = await Post.all().offset(pagination.offset).limit(pagination.limit)
        return {
            "items": [PostResponse.model_validate(p).model_dump() for p in items],
            "total": total,
            "page": pagination.page,
            "limit": pagination.limit,
        }

    @route.post("/", status_code=201)
    async def create(self, payload: PostCreate, user: CurrentUser) -> dict:
        post = await Post.create(**payload.model_dump(), author_id=int(user.id))
        return PostResponse.model_validate(post).model_dump()

    @route.get("/{post_id}")
    async def show(self, post_id: int) -> dict:
        post = await Post.get_or_none(id=post_id)
        if not post:
            raise HTTPException(404, "Post not found")
        return PostResponse.model_validate(post).model_dump()

    @route.patch("/{post_id}")
    async def update(self, post_id: int, payload: PostUpdate, user: CurrentUser) -> dict:
        post = await Post.get_or_none(id=post_id, author_id=int(user.id))
        if not post:
            raise HTTPException(404)
        await post.update_from_dict(payload.model_dump(exclude_none=True)).save()
        return PostResponse.model_validate(post).model_dump()

    @route.delete("/{post_id}", status_code=204)
    async def destroy(self, post_id: int, user: CurrentUser):
        deleted = await Post.filter(id=post_id, author_id=int(user.id)).delete()
        if not deleted:
            raise HTTPException(404)
''',

"redis_event": '''\
# Redis pub/sub event — fan-out to all running workers

# app/events/order_shipped_event.py
from forgeapi import Event

class OrderShipped(Event):
    background = True
    redis      = True
    redis_type = "pubsub"
    ttl        = 300  # dedup: only one worker processes per event_id

    def __init__(self, order_id: int, customer_email: str) -> None:
        self.order_id       = order_id
        self.customer_email = customer_email


# app/listeners/order_shipped_listener.py
from forgeapi import listen
from app.events.order_shipped_event import OrderShipped

@listen(OrderShipped)
async def send_confirmation_email(event: OrderShipped) -> None:
    await email_service.send(event.customer_email, f"Order {event.order_id} shipped!")


# main.py — lifespan setup
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from forgeapi import Core, EventBus

@asynccontextmanager
async def lifespan(app):
    bus = EventBus.get_instance()
    await bus.redis_connect("redis://localhost:6379")
    task = asyncio.create_task(bus.start_redis_subscriber())
    yield
    task.cancel()
    await bus.redis_disconnect()

app = FastAPI(lifespan=lifespan)
Core(app, auth="jwt", events=True)


# Dispatch from a controller:
await OrderShipped(order_id=42, customer_email="alice@example.com").dispatch()
''',

"stream_event": '''\
# Redis Streams event — persistent, survives worker restart

# app/events/order_event.py
from forgeapi import Event

class OrderEvent(Event):
    background = True
    redis      = True
    redis_type = "stream"
    namespace  = "shop"   # stream key = "shop:OrderEvent"

    def __init__(self, order_id: int, total: float, status: str) -> None:
        self.order_id = order_id
        self.total    = total
        self.status   = status


# Publisher (FastAPI service) — dispatch like any event:
# await OrderEvent(order_id=1, total=99.0, status="paid").dispatch()


# Standalone consumer worker (e.g. a bot or warehouse service)
# worker.py
import asyncio
from forgeapi import EventBus
from app.events.order_event import OrderEvent

async def main():
    bus = EventBus.get_instance()
    await bus.redis_connect("redis://localhost:6379")

    @bus.on(OrderEvent)
    async def handle_order(event: OrderEvent) -> None:
        print(f"Processing order {event.order_id}, total={event.total}")
        await warehouse.fulfill(event.order_id)

    await bus.start_stream_subscriber(
        group="warehouse_group",
        consumer="worker_1",
        event_classes=[OrderEvent],
    )

if __name__ == "__main__":
    asyncio.run(main())


# Multiple independent consumers (both receive every message):
# group="email_group", consumer="email_worker_1"
# group="analytics_group", consumer="analytics_worker_1"
''',

"jwt_auth": '''\
# JWT auth — login, refresh, protected route

# database/models/user.py
import hashlib
from tortoise import fields
from tortoise.models import Model

class User(Model):
    id         = fields.IntField(primary_key=True)
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


# app/schemas/auth.py
from pydantic import BaseModel
from forgeapi import BaseCreateSchema

class RegisterPayload(BaseCreateSchema):
    email: str
    password: str
    username: str

class LoginPayload(BaseModel):
    email: str
    password: str

class RefreshPayload(BaseModel):
    refresh_token: str


# app/controllers/auth_controller.py
from fastapi import HTTPException
from forgeapi.controllers import Controller, route
from forgeapi.auth import CurrentUser, auth
from forgeapi.exceptions import TokenExpiredError, TokenInvalidError
from database.models.user import User
from app.schemas.auth import RegisterPayload, LoginPayload, RefreshPayload


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
        access  = auth.create_access_token({"sub": str(user.id), "username": user.username})
        refresh = auth.create_refresh_token({"sub": str(user.id)})
        return {"access_token": access, "refresh_token": refresh, "token_type": "bearer"}

    @route.post("/login")
    async def login(self, payload: LoginPayload) -> dict:
        user = await User.get_or_none(email=payload.email)
        if not user or not user.verify_password(payload.password):
            raise HTTPException(401, "Invalid credentials")
        if not user.is_active:
            raise HTTPException(403, "Account disabled")
        access  = auth.create_access_token({"sub": str(user.id), "username": user.username})
        refresh = auth.create_refresh_token({"sub": str(user.id)})
        return {"access_token": access, "refresh_token": refresh, "token_type": "bearer"}

    @route.post("/refresh")
    async def refresh(self, payload: RefreshPayload) -> dict:
        try:
            data = auth.decode(payload.refresh_token, expected_type="refresh")
        except TokenExpiredError:
            raise HTTPException(401, "Refresh token expired")
        except TokenInvalidError:
            raise HTTPException(401, "Invalid refresh token")
        access = auth.create_access_token({"sub": data["sub"]})
        return {"access_token": access, "token_type": "bearer"}

    @route.get("/me")
    async def me(self, user: CurrentUser) -> dict:
        db_user = await User.get_or_none(id=int(user.id))
        if not db_user:
            raise HTTPException(404)
        return {"id": db_user.id, "email": db_user.email, "username": db_user.username}
''',

"rbac": '''\
# Full RBAC — model, seeder, protected routes

# database/models/user.py
from tortoise import fields
from forgeapi.permissions import PermissionsMixin

class User(PermissionsMixin):
    id        = fields.IntField(primary_key=True)
    email     = fields.CharField(max_length=255, unique=True)
    username  = fields.CharField(max_length=100)
    is_active = fields.BooleanField(default=True)

    class Meta:
        table = "users"


# database/seeds/roles_seeder.py
from forgeapi.database import Seeder
from forgeapi.permissions.models import Permission, Role
from database.models.user import User

class RolesSeeder(Seeder):
    async def run(self) -> None:
        for name in ["create:posts", "edit:posts", "delete:posts", "publish:posts", "admin:panel"]:
            await Permission.find_or_create(name)

        editor = await Role.find_or_create("editor")
        await editor.give_permission("create:posts", "edit:posts")

        admin = await Role.find_or_create("admin")
        await admin.give_permission("create:posts", "edit:posts", "delete:posts", "publish:posts", "admin:panel")

        user = await User.get_or_none(id=1)
        if user:
            await user.assign_role("admin")


# app/controllers/post_controller.py
from fastapi import HTTPException
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
    async def create(self, payload: PostCreate, user=require_permission("create:posts")):
        post = await Post.create(**payload.model_dump(), author_id=user.id)
        return {"id": post.id}

    @route.delete("/{post_id}", status_code=204)
    async def destroy(self, post_id: int, user=require_permission("delete:posts", "admin:panel")):
        # OR logic — user must have at least one of the listed permissions
        await Post.filter(id=post_id).delete()

    @route.get("/admin/stats")
    async def admin_stats(self, user=require_role("admin")) -> dict:
        return {"total_posts": await Post.all().count(), "admin_id": user.id}

    # Manual permission check inside a method:
    @route.patch("/{post_id}")
    async def update(self, post_id: int, payload: PostUpdate, user: CurrentUser) -> dict:
        db_user = await User.get(id=int(user.id))
        if not await db_user.can("edit:posts"):
            raise HTTPException(403, "Forbidden")
        post = await Post.get_or_none(id=post_id)
        if not post:
            raise HTTPException(404)
        await post.update_from_dict(payload.model_dump(exclude_none=True)).save()
        return {"id": post.id}
''',

"pagination": '''\
# Pagination — full example with total count and search

# app/controllers/product_controller.py
import asyncio
from fastapi import HTTPException
from forgeapi.controllers import Controller, route
from forgeapi.pagination import Pagination
from database.models.product import Product
from app.schemas.product import ProductResponse


class ProductController(Controller):
    prefix = "/products"
    tags   = ["products"]

    @route.get("/")
    async def index(self, pagination: Pagination) -> dict:
        total, items = await asyncio.gather(
            Product.all().count(),
            Product.all()
                   .order_by("-created_at")
                   .offset(pagination.offset)
                   .limit(pagination.limit),
        )
        return {
            "items": [ProductResponse.model_validate(p).model_dump() for p in items],
            "total": total,
            "page": pagination.page,
            "limit": pagination.limit,
            "pages": -(-total // pagination.limit),  # ceiling division
        }

    @route.get("/search")
    async def search(self, q: str, pagination: Pagination) -> dict:
        qs = Product.filter(name__icontains=q)
        total, items = await asyncio.gather(
            qs.count(),
            qs.offset(pagination.offset).limit(pagination.limit),
        )
        return {"items": items, "total": total, "page": pagination.page}


# Configure in main.py:
# Core(app, pagination=20)  ← sets default_limit=20
# or forgeapi.toml:
# [pagination]
# default_limit = 20
# max_limit = 100
''',

"guard": '''\
# Guards — API key guard, active-user guard, role guard

# app/guards/api_key_guard.py
from fastapi import HTTPException, Request
from forgeapi.middleware import Guard

class ApiKeyGuard(Guard):
    def __init__(self, header: str = "X-API-Key"):
        self.header = header

    async def handle(self, request: Request) -> None:
        key = request.headers.get(self.header)
        if not key or key != "expected-secret":
            raise HTTPException(403, "Invalid or missing API key")


# app/guards/active_user_guard.py
from fastapi import HTTPException
from forgeapi.middleware import Guard
from forgeapi.auth import CurrentUser

class ActiveUserGuard(Guard):
    async def handle(self, user: CurrentUser) -> None:
        if not getattr(user, "is_active", True):
            raise HTTPException(403, "Account is disabled")


# app/guards/admin_guard.py
from fastapi import HTTPException
from forgeapi.middleware import Guard
from forgeapi.auth import CurrentUser
from database.models.user import User

class AdminGuard(Guard):
    async def handle(self, user: CurrentUser) -> None:
        db_user = await User.get_or_none(id=int(user.id))
        if not db_user or not await db_user.has_role("admin"):
            raise HTTPException(403, "Admins only")


# Per-route usage:
from fastapi import Depends
from forgeapi.controllers import Controller, route

class WebhookController(Controller):
    prefix = "/webhooks"
    tags   = ["webhooks"]

    @route.post("/stripe", dependencies=[Depends(ApiKeyGuard(header="X-Stripe-Signature"))])
    async def stripe(self, payload: dict) -> dict:
        return {"received": True}


# Per-controller usage (every route protected):
class AdminController(Controller):
    prefix = "/admin"
    tags   = ["admin"]
    guards = [ActiveUserGuard(), AdminGuard()]

    @route.get("/stats")
    async def stats(self) -> dict:
        return {"users": await User.all().count()}
''',

}


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@mcp.tool()
def get_docs(topic: str) -> str:
    """Return inline API documentation for a forge-kits topic.

    Topics: core, controllers, events, auth, permissions, pagination, schemas,
            middleware, cli, config

    Args:
        topic: One of the topic names listed above (case-insensitive).

    Returns:
        Markdown documentation string covering the topic's full API.
    """
    key = topic.lower().strip()
    doc = _DOCS.get(key)
    if doc:
        return doc
    available = ", ".join(sorted(_DOCS.keys()))
    return (
        f"Unknown topic '{topic}'. Available topics: {available}\n\n"
        "Try one of the listed topics — each returns complete API docs."
    )


@mcp.tool()
def get_example(pattern: str) -> str:
    """Return a complete working code example for a forge-kits pattern.

    Patterns: crud_controller, redis_event, stream_event, jwt_auth, rbac,
              pagination, guard

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


@mcp.tool()
def generate_controller(name: str, routes: list[str]) -> str:
    """Generate a forge-kits Controller class.

    Args:
        name:   Resource name in PascalCase, e.g. "Post", "AdminUser".
                Must start with a letter and contain only letters/digits.
        routes: List of route descriptors in "METHOD /path" format.
                Supported methods: GET, POST, PUT, PATCH, DELETE.
                Examples: ["GET /", "POST /", "GET /{id}", "PATCH /{id}", "DELETE /{id}"]

    Returns:
        Python source code for the controller file.
    """
    if not re.match(r'^[A-Za-z][A-Za-z0-9]*$', name):
        return "Error: name must start with a letter and contain only letters and digits."

    words = re.findall(r'[A-Z][a-z0-9]*', name)

    def pluralize(s: str) -> str:
        if s.endswith("y") and len(s) >= 2 and s[-2] not in "aeiou":
            return s[:-1] + "ies"
        if s.endswith("s"):
            return s
        return s + "s"

    if len(words) >= 2:
        namespace   = words[0].lower()
        resource    = "-".join(w.lower() for w in words[1:])
        prefix      = f"/{namespace}/{pluralize(resource)}"
        tags        = [f"{namespace}/{pluralize(resource)}"]
    else:
        slug   = words[0].lower() if words else name.lower()
        prefix = f"/{pluralize(slug)}"
        tags   = [pluralize(slug)]

    method_map = {"GET": "get", "POST": "post", "PUT": "put", "PATCH": "patch", "DELETE": "delete"}

    route_defs: list[dict] = []
    for r in routes:
        parts = r.strip().split(None, 1)
        if len(parts) != 2:
            continue
        http_method = parts[0].upper()
        path = parts[1]
        if http_method not in method_map:
            continue

        path_params = re.findall(r'\{(\w+)\}', path)

        if path == "/":
            fn_name = {"GET": "index", "POST": "create"}.get(http_method, http_method.lower())
        else:
            slugs = [p.strip("{}").replace("-", "_") for p in path.strip("/").split("/") if p]
            param = slugs[-1] if slugs else "item"
            fn_name = {
                "GET": f"show_{param}",
                "PUT": f"update_{param}",
                "PATCH": f"update_{param}",
                "DELETE": f"destroy_{param}",
            }.get(http_method, f"{http_method.lower()}_{param}")

        route_defs.append({
            "decorator": method_map[http_method],
            "path": path,
            "fn_name": fn_name,
            "http_method": http_method,
            "path_params": path_params,
            "status_code": 201 if http_method == "POST" else (204 if http_method == "DELETE" else None),
        })

    lines = [
        "from fastapi import HTTPException",
        "from forgeapi.controllers import Controller, route",
        "from forgeapi.auth import CurrentUser, OptionalUser",
        "from forgeapi.pagination import Pagination",
        "",
        "",
        f"class {name}Controller(Controller):",
        f'    prefix = "{prefix}"',
        f'    tags   = {tags!r}',
    ]

    if not route_defs:
        lines += ["", '    @route.get("/")', "    async def index(self, pagination: Pagination) -> dict:", "        pass"]
    else:
        for rd in route_defs:
            lines.append("")
            sc = f", status_code={rd['status_code']}" if rd["status_code"] else ""
            lines.append(f'    @route.{rd["decorator"]}("{rd["path"]}"{sc})')

            sig = ["self"] + [f"{p}: int" for p in rd["path_params"]]
            if rd["http_method"] in ("POST", "PUT", "PATCH"):
                payload = name + ("Create" if rd["http_method"] == "POST" else "Update") + "Payload"
                sig.append(f"payload: {payload}")
            if rd["http_method"] != "GET":
                sig.append("user: CurrentUser")
            elif rd["path"] == "/" and rd["http_method"] == "GET":
                sig.append("pagination: Pagination")

            ret = "" if rd["http_method"] == "DELETE" else " -> dict"
            lines.append(f"    async def {rd['fn_name']}({', '.join(sig)}){ret}:")
            lines.append("        pass")

    return "\n".join(lines) + "\n"


@mcp.tool()
def generate_event(name: str, fields: list[str]) -> str:
    """Generate an Event class and its listener file.

    Args:
        name:   Event name in PascalCase without the "Event" suffix,
                e.g. "UserRegistered", "OrderShipped".
        fields: List of field definitions in "name:type" format,
                e.g. ["user_id:int", "email:str", "plan:str"].
                Supported types: int, str, float, bool, dict, list.

    Returns:
        Python source containing the Event subclass and a companion listener.
    """
    if not re.match(r'^[A-Za-z][A-Za-z0-9]*$', name):
        return "Error: name must start with a letter and contain only letters and digits."

    parsed: list[tuple[str, str]] = []
    for f in fields:
        fname, ftype = (f.split(":", 1) if ":" in f else (f, "str"))
        fname, ftype = fname.strip(), ftype.strip()
        if re.match(r'^\w+$', fname):
            parsed.append((fname, ftype))

    snake = re.sub(r'(?<!^)(?=[A-Z])', '_', name).lower()

    event_lines = [
        f"# app/events/{snake}_event.py",
        "from forgeapi import Event",
        "",
        "",
        f"class {name}Event(Event):",
        "    background = True",
        "    redis      = False",
        "",
    ]

    if parsed:
        init_args = ", ".join(f"{fn}: {ft}" for fn, ft in parsed)
        event_lines.append(f"    def __init__(self, {init_args}) -> None:")
        for fn, _ in parsed:
            event_lines.append(f"        self.{fn} = {fn}")
    else:
        event_lines += ["    def __init__(self) -> None:", "        pass"]

    listener_lines = [
        "",
        "",
        f"# app/listeners/{snake}_listener.py",
        "from forgeapi import listen",
        f"from app.events.{snake}_event import {name}Event",
        "",
        "",
        f"@listen({name}Event)",
        f"async def handle_{snake}(event: {name}Event) -> None:",
        "    pass",
    ]

    dispatch_args = ", ".join(f"{fn}=..." for fn, _ in parsed)
    dispatch_lines = [
        "",
        "",
        f"# await {name}Event({dispatch_args}).dispatch()",
    ]

    return "\n".join(event_lines + listener_lines + dispatch_lines) + "\n"


@mcp.tool()
def generate_schema(name: str, fields: list[str], mode: str = "all") -> str:
    """Generate Pydantic schema classes for forge-kits.

    Args:
        name:   Resource name in PascalCase, e.g. "Post", "UserProfile".
        fields: Field definitions in "name:type" or "name:type=default" format.
                Examples: ["title:str", "body:str", "views:int=0", "tags:list[str]=[]"].
        mode:   "all" | "response" | "create" | "update" | "crud"
                "all"/"crud" → all three classes; others → single class.

    Returns:
        Python source code with the requested schema classes.
    """
    if not re.match(r'^[A-Za-z][A-Za-z0-9]*$', name):
        return "Error: name must start with a letter and contain only letters and digits."

    parsed: list[tuple[str, str, str | None]] = []
    for f in fields:
        default = None
        if "=" in f:
            left, default = f.rsplit("=", 1)
            default = default.strip()
        else:
            left = f
        fname, ftype = (left.split(":", 1) if ":" in left else (left, "str"))
        fname, ftype = fname.strip(), ftype.strip()
        if re.match(r'^\w+$', fname):
            parsed.append((fname, ftype, default))

    mode = mode.lower().strip()
    gen_response = mode in ("all", "crud", "response")
    gen_create   = mode in ("all", "crud", "create")
    gen_update   = mode in ("all", "crud", "update")

    if not any([gen_response, gen_create, gen_update]):
        return f"Error: unknown mode '{mode}'. Use: all, response, create, update, crud."

    lines = ["from forgeapi import BaseSchema, BaseCreateSchema, BaseUpdateSchema", ""]

    if gen_response:
        lines += ["", f"class {name}Response(BaseSchema):",
                  "    # Inherits: id, created_at, updated_at — model_config from_attributes=True"]
        lines += ([f"    {fn}: {ft}" + (f" = {d}" if d else "") for fn, ft, d in parsed] or ["    pass"])

    if gen_create:
        lines += ["", f"class {name}CreatePayload(BaseCreateSchema):"]
        lines += ([f"    {fn}: {ft}" + (f" = {d}" if d else "") for fn, ft, d in parsed] or ["    pass"])

    if gen_update:
        lines += ["", f"class {name}UpdatePayload(BaseUpdateSchema):",
                  "    # All fields Optional — safe for partial PATCH"]
        lines += ([f"    {fn}: {ft} | None = None" for fn, ft, _ in parsed] or ["    pass"])

    return "\n".join(lines) + "\n"


@mcp.tool()
def project_info(path: str = ".") -> str:
    """Read a user's forgeapi.toml and return project structure information.

    Args:
        path: Path to the project directory or directly to forgeapi.toml.
              Defaults to the current directory.

    Returns:
        Formatted project configuration and directory structure summary.
    """
    given = Path(path).expanduser().resolve()
    toml_path = given if (given.is_file() and given.name == "forgeapi.toml") else given / "forgeapi.toml"

    if not toml_path.exists():
        return (
            f"No forgeapi.toml found at '{given}'.\n\n"
            "Create one with: forgeapi init <project-name>\n"
            "Or run in a directory that contains forgeapi.toml."
        )

    try:
        with open(toml_path, "rb") as fh:
            raw = tomllib.load(fh)
    except Exception as exc:
        return f"Error reading forgeapi.toml: {exc}"

    root = toml_path.parent
    defaults = {
        "models_dir": "database/models", "controllers_dir": "app/controllers",
        "schemas_dir": "app/schemas", "events_dir": "app/events",
        "listeners_dir": "app/listeners", "seeds_dir": "database/seeds",
        "base_prefix": "/api/v1",
    }
    struct = {**defaults, **raw.get("structure", {})}
    proj   = raw.get("project", {})
    auth   = {**{"strategy": "jwt", "jwt_secret_env": "JWT_SECRET", "access_ttl_minutes": 30}, **raw.get("auth", {})}
    pag    = {**{"default_limit": 20, "max_limit": 100}, **raw.get("pagination", {})}

    lines = [f"# forge-kits project: {toml_path}", "",
             "## Project",
             f"  name    = {proj.get('name', 'my-app')!r}",
             f"  version = {proj.get('version', '0.1.0')!r}", "",
             "## Structure"]

    for key, val in struct.items():
        marker = ""
        if key != "base_prefix":
            marker = " [exists]" if (root / val).exists() else " [missing]"
        lines.append(f"  {key:<20} = {val!r}{marker}")

    lines += ["", "## Auth",
              f"  strategy           = {auth['strategy']!r}",
              f"  jwt_secret_env     = {auth['jwt_secret_env']!r}",
              f"  access_ttl_minutes = {auth['access_ttl_minutes']}", "",
              "## Pagination",
              f"  default_limit = {pag['default_limit']}",
              f"  max_limit     = {pag['max_limit']}", ""]

    for label, dir_key, glob in [
        ("Controllers", "controllers_dir", "*_controller.py"),
        ("Events",      "events_dir",      "*_event.py"),
        ("Listeners",   "listeners_dir",   "*_listener.py"),
    ]:
        d = root / struct[dir_key]
        if d.exists():
            files = sorted(d.rglob(glob))
            if files:
                lines.append(f"## {label} found")
                for f in files:
                    try:
                        lines.append(f"  {f.relative_to(root)}")
                    except ValueError:
                        lines.append(f"  {f}")
                lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
