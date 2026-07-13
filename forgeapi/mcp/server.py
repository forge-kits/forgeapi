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

mcp = FastMCP(
    "forge-kits",
    instructions="""\
forge-kits CLI and API toolkit for FastAPI.

RULES — must follow for every forge-kits project:
- Dev server: `forgeapi runserver --reload` — NEVER uvicorn directly
- Migrations: `forgeapi db:*` — NEVER aerich, NEVER pip install aerich
- Code generation: `forgeapi make:*` — prefer CLI over writing files manually

Start every session: call scan_project('.') then get_docs('cheatsheet').
For advanced topics call get_docs with: workflow, core, controllers, events,
auth, permissions, schemas, middleware, cli, config, models,
tortoise (basic), tortoise_advanced (Q/prefetch/transactions).
""",
)

# ---------------------------------------------------------------------------
# Topic docs database
# ---------------------------------------------------------------------------

_DOCS: dict[str, str] = {

"cheatsheet": """\
# forge-kits cheatsheet

## Controller skeleton
```python
class PostController(Controller):
    prefix = "/posts"; tags = ["posts"]

    @route.get("/")
    async def index(self, pagination: Pagination) -> dict:
        total, items = await asyncio.gather(Post.all().count(),
            Post.all().order_by("-created_at").offset(pagination.offset).limit(pagination.limit))
        return {"items": items, "total": total, "page": pagination.page}

    @route.post("/", status_code=201)
    async def create(self, payload: PostCreate, user: CurrentUser) -> dict:
        post = await Post.create(**payload.model_dump(), author_id=int(user.id))
        return PostResponse.model_validate(post).model_dump()

    @route.get("/{id}")
    async def show(self, id: int) -> dict:
        post = await Post.get_or_none(id=id)
        if not post: raise HTTPException(404)
        return PostResponse.model_validate(post).model_dump()

    @route.patch("/{id}")
    async def update(self, id: int, payload: PostUpdate, user: CurrentUser) -> dict:
        post = await Post.get_or_none(id=id, author_id=int(user.id))
        if not post: raise HTTPException(404)
        await post.update_from_dict(payload.model_dump(exclude_none=True)).save()
        return PostResponse.model_validate(post).model_dump()

    @route.delete("/{id}", status_code=204)
    async def destroy(self, id: int, user: CurrentUser):
        if not await Post.filter(id=id, author_id=int(user.id)).delete(): raise HTTPException(404)
```

## Schemas | Auth | Event
```python
class PostResponse(BaseSchema): title: str          # + id/created_at/updated_at inherited
class PostCreate(BaseCreateSchema): title: str
class PostUpdate(BaseUpdateSchema): title: str | None = None  # auto-optional

user: CurrentUser   # 401 if missing  |  user: OptionalUser  # None if missing
access = auth.create_access_token({"sub": str(user.id), "username": user.username})

class OrderShipped(Event):
    background = True
    def __init__(self, order_id: int) -> None: self.order_id = order_id

@listen(OrderShipped)
async def handle(event: OrderShipped) -> None: ...
await OrderShipped(order_id=1).dispatch()
```

## Common queries
```python
post  = await Post.get_or_none(id=id)
posts = await Post.filter(is_active=True).order_by("-created_at").offset(0).limit(20)
total = await Post.filter(is_active=True).count()
post  = await Post.create(**payload.model_dump(), author_id=int(user.id))
await post.update_from_dict(payload.model_dump(exclude_none=True)).save()
await Post.filter(author_id=1).update(is_active=False); await post.delete()
```

## CLI
```bash
forgeapi make:controller Post && forgeapi make:model Post
forgeapi make:event OrderShipped   # → event + listener files
forgeapi generate:schema Post --payload --response
forgeapi db:makemigrations && forgeapi db:migrate
forgeapi runserver --reload        # NOT uvicorn directly
```
""",

"workflow": """\
# forge-kits: Workflow rules for Claude

## ALWAYS use forgeapi CLI — never the underlying tool directly

| Task | Command to use | NEVER do this |
|------|---------------|---------------|
| Start dev server | `forgeapi runserver --reload` | `uvicorn main:app --reload` |
| DB: init migrations | `forgeapi db:init` | `aerich init` |
| DB: create migration | `forgeapi db:makemigrations` | `aerich migrate --name ...` |
| DB: apply migrations | `forgeapi db:migrate` | `aerich upgrade` |
| Generate controller | `forgeapi make:controller Post` | writing files manually |
| Generate model | `forgeapi make:model Post` | writing files manually |
| Generate event | `forgeapi make:event OrderShipped` | writing files manually |

## DO NOT install or reference aerich

forge-kits wraps migrations through `forgeapi db:*`. Do NOT:
- `pip install aerich`
- Add `aerich` to `pyproject.toml` or `requirements.txt`
- Run `aerich` commands directly

## DO NOT run uvicorn directly

Always use the `forgeapi runserver` abstraction:
```bash
forgeapi runserver                       # localhost:8000
forgeapi runserver --reload              # with auto-reload (development)
forgeapi runserver --port 9000           # custom port
forgeapi runserver --host 0.0.0.0 --port 8080
```

## Canonical new-project setup sequence

```bash
forgeapi init my-project        # scaffold project (interactive prompts)
cd my-project
pip install -e .                # or: uv sync
forgeapi db:init                # init migration config
forgeapi db:makemigrations      # generate first migration
forgeapi db:migrate             # apply migrations
forgeapi runserver --reload     # start dev server
```

## Code-generation reference (prefer CLI over manual files)

```bash
forgeapi make:controller Post         # app/controllers/post_controller.py
forgeapi make:controller AdminUser    # app/controllers/admin/user_controller.py
forgeapi make:model Post              # database/models/post.py
forgeapi make:event OrderShipped      # app/events/order_shipped_event.py
forgeapi make:listener OrderShipped   # app/listeners/order_shipped_listener.py
forgeapi make:seed User               # database/seeds/user_seeder.py
forgeapi generate:schema Post --payload --response
```
""",

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

## Running the dev server

```bash
forgeapi runserver --reload    # always use this — NOT uvicorn main:app directly
forgeapi runserver --port 9000 --host 0.0.0.0
```

## DB migrations (after defining models)

```bash
forgeapi db:init
forgeapi db:makemigrations
forgeapi db:migrate
```
Do NOT install or run aerich directly — forgeapi db:* handles everything.
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

Use these — NEVER run aerich commands or install aerich directly.

```
forgeapi db:init                        # initialise migration config
forgeapi db:makemigrations [-n <name>]  # generate a new migration
forgeapi db:migrate                     # apply pending migrations
forgeapi db:downgrade                   # revert last migration
forgeapi db:history                     # show migration log
forgeapi db:seed                        # run all seeders
forgeapi db:seed User Post              # run specific seeders by class name
forgeapi db:fresh                       # TRUNCATE all tables (asks confirmation)
forgeapi db:fresh --force               # DROP all tables (irreversible)
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

"models": """\
# forge-kits: Tortoise ORM Models

## Basic model structure
```python
from tortoise import fields
from tortoise.models import Model

class Post(Model):
    id         = fields.IntField(primary_key=True)   # auto-added if omitted
    title      = fields.CharField(max_length=255)
    body       = fields.TextField()
    is_active  = fields.BooleanField(default=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "posts"            # defaults to lowercase class name
        ordering = ["-created_at"] # default QuerySet ordering
```

## All field types
```python
# Numeric
fields.IntField(primary_key=True)    # int, auto-increment PK
fields.BigIntField()                  # 64-bit int
fields.SmallIntField()                # 16-bit int
fields.FloatField()                   # double precision
fields.DecimalField(max_digits=10, decimal_places=2)

# String
fields.CharField(max_length=255)
fields.TextField()                    # unlimited
fields.UUIDField()                    # uuid.UUID, auto if pk=True

# Date/time
fields.DatetimeField(auto_now_add=True)  # set on create
fields.DatetimeField(auto_now=True)      # update on every save
fields.DateField()
fields.TimeField()

# Other
fields.BooleanField(default=False)
fields.JSONField(default=dict)        # stored as JSON string
fields.BinaryField()                  # bytes

# Nullable / optional
fields.CharField(max_length=100, null=True)
fields.IntField(null=True)
```

## Relationships
```python
class Post(Model):
    # Many-to-one (FK)
    author = fields.ForeignKeyField(
        "models.User",              # "app_label.ModelName"
        related_name="posts",       # reverse accessor: user.posts.all()
        on_delete=fields.CASCADE,   # CASCADE | SET_NULL | SET_DEFAULT | RESTRICT | NO_ACTION
        null=True,                  # optional FK
    )
    author_id: int                  # raw FK column (auto-available as {field}_id)

    # Many-to-many
    tags = fields.ManyToManyField(
        "models.Tag",
        related_name="posts",
        through="post_tags",        # optional explicit through table name
    )

    # One-to-one
    profile = fields.OneToOneField("models.Profile", related_name="user")
```

Access reverse relations:
```python
# FK reverse (BackwardFKRelation) — always needs await or prefetch
posts = await user.posts.all()
posts = await user.posts.filter(is_active=True).order_by("-created_at")

# M2M — same syntax
tags = await post.tags.all()
await post.tags.add(tag)       # add to M2M
await post.tags.remove(tag)    # remove from M2M
await post.tags.clear()        # remove all
```

## Meta class options
```python
class Meta:
    table = "my_posts"                    # explicit table name
    ordering = ["-created_at", "title"]   # default sort
    unique_together = [("author_id", "slug")]
    indexes = [("title",), ("author_id", "created_at")]
    abstract = True                       # base class, no table
```

## database/models/__init__.py
```python
from .user import User
from .post import Post
# add every new model here — Tortoise discovers via this package
```

## TORTOISE_ORM config → see get_docs('config')
## Migrations → see get_docs('workflow') or get_docs('cli')
""",

"tortoise": """\
# forge-kits: Tortoise ORM — Basic queries

## CRUD
```python
post = await Post.create(**payload.model_dump(), author_id=int(user.id))
post, created = await Post.get_or_create(slug="x", defaults={"title": "X"})
post = await Post.get(id=1)           # raises DoesNotExist
post = await Post.get_or_none(id=1)  # None if missing
post.title = "New"; await post.save()
await post.update_from_dict(payload.model_dump(exclude_none=True)).save()
await post.delete()
```

## Filter / order / paginate
```python
posts  = await Post.filter(is_active=True, author_id=1).order_by("-created_at").offset(0).limit(20)
total  = await Post.all().count()
exists = await Post.filter(slug="x").exists()
first  = await Post.filter(is_active=True).first()

# bulk ops
await Post.filter(author_id=1).update(is_active=False)
await Post.filter(author_id=1).delete()
```

## Lookup suffixes
```python
Post.filter(title__icontains="hello")  # ILIKE %hello%
Post.filter(created_at__gte=dt)        # >=
Post.filter(id__in=[1, 2, 3])          # IN
Post.filter(author_id__isnull=False)   # IS NOT NULL
Post.exclude(is_active=False)
```

## Async gather (parallel queries — use in every index/list endpoint)
```python
import asyncio
total, items = await asyncio.gather(
    Post.filter(is_active=True).count(),
    Post.filter(is_active=True).order_by("-created_at").offset(pagination.offset).limit(pagination.limit),
)
```

For advanced queries (Q objects, prefetch_related, annotate, bulk_create, transactions, raw SQL)
call get_docs('tortoise_advanced').
""",

"tortoise_advanced": """\
# forge-kits: Tortoise ORM — Advanced queries

## Q objects (OR / NOT)
```python
from tortoise.expressions import Q
Post.filter(Q(title__icontains="py") | Q(body__icontains="py"))
Post.filter(~Q(is_active=False))
Post.filter(Q(author_id=1) & Q(is_active=True))
```

## Prefetch relations (avoids N+1 queries)
```python
posts = await Post.all().prefetch_related("author", "tags")
for p in posts:
    print(p.author.username)         # no extra query
    print([t.name for t in p.tags])  # no extra query

posts = await Post.all().select_related("author")          # JOIN (FK/O2O only)
posts = await Post.all().prefetch_related("author__profile")  # nested
```

## values / values_list
```python
rows = await Post.filter(is_active=True).values("id", "title", "author_id")
# → [{"id": 1, "title": "Hello", ...}, ...]

ids = await Post.all().values_list("id", flat=True)
# → [1, 2, 3, ...]
```

## Aggregations
```python
from tortoise.functions import Count, Sum, Max, Min, Avg

total = await Post.all().count()
result = await Post.annotate(n=Count("id")).group_by("author_id").values("author_id", "n")
max_id = await Post.all().annotate(m=Max("id")).values("m")
```

## Bulk create
```python
posts = [Post(title=f"Post {i}", author_id=1) for i in range(100)]
await Post.bulk_create(posts, batch_size=50)
await Post.bulk_create(posts, update_fields=["title"], on_conflict=["slug"])
```

## Transactions
```python
from tortoise import transactions

async with transactions.in_transaction():
    user = await User.create(email="alice@example.com")
    await Profile.create(user_id=user.id, bio="Hello")

from tortoise.transactions import atomic

@atomic()
async def register(email: str) -> User:
    user = await User.create(email=email)
    await Profile.create(user_id=user.id)
    return user
```

## Raw SQL
```python
from tortoise import Tortoise
conn = Tortoise.get_connection("default")
rows = await conn.execute_query_dict(
    "SELECT id, title FROM posts WHERE author_id = $1", [user_id]
)
```
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

    IMPORTANT: Call get_docs('workflow') FIRST when starting any forge-kits project
    or task — it contains critical rules about which CLI commands to use and which
    to avoid (e.g. never use uvicorn or aerich directly).

    Start with 'cheatsheet' — covers 80% of tasks in ~200 tokens.
    Only call specific topics when you need more detail.

    Topics (lightest → heaviest):
      cheatsheet       ~200 tok  controller+queries+auth+events quick ref
      workflow         ~560 tok  CLI rules, canonical project setup
      pagination       ~320 tok
      config           ~450 tok  forgeapi.toml + TORTOISE_ORM config
      schemas          ~570 tok
      middleware       ~525 tok
      core             ~645 tok
      cli              ~660 tok
      auth             ~800 tok
      permissions      ~810 tok
      controllers      ~935 tok
      events           ~965 tok
      tortoise         ~400 tok  basic CRUD + filter (call this first)
      tortoise_advanced~550 tok  Q objects, prefetch, transactions, raw SQL
      models           ~900 tok  field types, relationships, Meta

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


# ---------------------------------------------------------------------------
# AST helpers for scan_project
# ---------------------------------------------------------------------------

def _ast_parse_safe(path: Path) -> "ast.Module | None":
    import ast
    try:
        return ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError:
        return None


def _node_name(node: object) -> str:
    import ast
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return f"{_node_name(node.value)}.{node.attr}"
    return ""


def _call_name(node: object) -> str:
    import ast
    if isinstance(node, ast.Call):
        return _node_name(node.func)
    return _node_name(node)


def _scan_models(files: list[Path], root: Path) -> list[str]:
    import ast
    out: list[str] = []
    model_bases = {"Model", "PermissionsMixin"}
    for f in files:
        tree = _ast_parse_safe(f)
        if not tree:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            bases = [_node_name(b) for b in node.bases]
            if not any(b in model_bases for b in bases):
                continue
            table = node.name.lower()
            fields: list[str] = []
            for item in node.body:
                if isinstance(item, ast.Assign):
                    for t in item.targets:
                        if not isinstance(t, ast.Name) or t.id.startswith("_"):
                            continue
                        fname = _call_name(item.value)
                        if fname and "field" in fname.lower():
                            # extract key kwargs for display
                            kwargs: list[str] = []
                            if isinstance(item.value, ast.Call):
                                for kw in item.value.keywords:
                                    if kw.arg in ("max_length", "null", "default", "primary_key",
                                                  "unique", "on_delete", "related_name"):
                                        if isinstance(kw.value, ast.Constant):
                                            kwargs.append(f"{kw.arg}={kw.value.value!r}")
                                        elif isinstance(kw.value, ast.Attribute):
                                            kwargs.append(f"{kw.arg}={_node_name(kw.value)}")
                            short = fname.split(".")[-1]
                            kw_str = f"({', '.join(kwargs)})" if kwargs else ""
                            fields.append(f"    {t.id}: {short}{kw_str}")
                if isinstance(item, ast.ClassDef) and item.name == "Meta":
                    for meta_item in item.body:
                        if isinstance(meta_item, ast.Assign):
                            for t in meta_item.targets:
                                if isinstance(t, ast.Name) and t.id == "table":
                                    if isinstance(meta_item.value, ast.Constant):
                                        table = meta_item.value.value
            try:
                rel = f.relative_to(root)
            except ValueError:
                rel = f
            out.append(f"  {node.name}  [table={table!r}]  ({rel})")
            if fields:
                out.extend(fields[:10])
                if len(fields) > 10:
                    out.append(f"    ... +{len(fields) - 10} more")
    return out


def _scan_controllers(files: list[Path], root: Path, base_prefix: str) -> list[str]:
    import ast
    out: list[str] = []
    for f in files:
        tree = _ast_parse_safe(f)
        if not tree:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            bases = [_node_name(b) for b in node.bases]
            if not any("Controller" in b for b in bases):
                continue
            prefix = None
            for item in node.body:
                if isinstance(item, ast.Assign):
                    for t in item.targets:
                        if isinstance(t, ast.Name) and t.id == "prefix":
                            if isinstance(item.value, ast.Constant):
                                prefix = item.value.value
            routes: list[str] = []
            for item in node.body:
                if not isinstance(item, ast.AsyncFunctionDef):
                    continue
                for dec in item.decorator_list:
                    method = path = None
                    if isinstance(dec, ast.Attribute) and _node_name(dec.value) == "route":
                        method = dec.attr.upper()
                        path = "/"
                    elif isinstance(dec, ast.Call):
                        func = dec.func
                        if isinstance(func, ast.Attribute) and _node_name(func.value) == "route":
                            method = func.attr.upper()
                            path = dec.args[0].value if dec.args and isinstance(dec.args[0], ast.Constant) else "/"
                    if method and path is not None:
                        full = f"{base_prefix}{prefix or ''}{path}".replace("//", "/")
                        routes.append(f"    {method:<6} {full}")
            try:
                rel = f.relative_to(root)
            except ValueError:
                rel = f
            out.append(f"  {node.name}  prefix={prefix or 'auto'}  ({rel})")
            out.extend(routes)
    return out


def _scan_schemas(files: list[Path], root: Path) -> list[str]:
    import ast
    schema_bases = {"BaseSchema", "BaseCreateSchema", "BaseUpdateSchema", "BaseModel"}
    out: list[str] = []
    for f in files:
        tree = _ast_parse_safe(f)
        if not tree:
            continue
        classes: list[str] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            bases = [_node_name(b) for b in node.bases]
            if any(b in schema_bases for b in bases):
                classes.append(f"    {node.name}({', '.join(bases)})")
        if classes:
            try:
                rel = f.relative_to(root)
            except ValueError:
                rel = f
            out.append(f"  {rel}:")
            out.extend(classes)
    return out


def _scan_events(files: list[Path], root: Path) -> list[str]:
    import ast
    out: list[str] = []
    for f in files:
        tree = _ast_parse_safe(f)
        if not tree:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            bases = [_node_name(b) for b in node.bases]
            if "Event" not in bases:
                continue
            flags: list[str] = []
            for item in node.body:
                if isinstance(item, ast.Assign):
                    for t in item.targets:
                        if isinstance(t, ast.Name) and t.id == "background":
                            if isinstance(item.value, ast.Constant) and item.value.value:
                                flags.append("background")
                        if isinstance(t, ast.Name) and t.id == "redis":
                            if isinstance(item.value, ast.Constant) and item.value.value:
                                redis_type = "pubsub"
                                for item2 in node.body:
                                    if isinstance(item2, ast.Assign):
                                        for t2 in item2.targets:
                                            if isinstance(t2, ast.Name) and t2.id == "redis_type":
                                                if isinstance(item2.value, ast.Constant):
                                                    redis_type = item2.value.value
                                flags.append(f"redis/{redis_type}")
            init_params: list[str] = []
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == "__init__":
                    for arg in item.args.args[1:]:
                        init_params.append(arg.arg)
            flag_str = f" [{', '.join(flags)}]" if flags else ""
            out.append(f"  {node.name}{flag_str}")
            if init_params:
                out.append(f"    fields: {', '.join(init_params)}")
    return out


def _scan_listeners(files: list[Path], root: Path) -> list[str]:
    import ast
    out: list[str] = []
    for f in files:
        tree = _ast_parse_safe(f)
        if not tree:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
                continue
            for dec in node.decorator_list:
                if (
                    isinstance(dec, ast.Call)
                    and isinstance(dec.func, ast.Name)
                    and dec.func.id == "listen"
                    and dec.args
                ):
                    event = _node_name(dec.args[0])
                    out.append(f"  {node.name}  →  {event}")
    return out


def _scan_seeders(files: list[Path], root: Path) -> list[str]:
    import ast
    out: list[str] = []
    for f in files:
        tree = _ast_parse_safe(f)
        if not tree:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            bases = [_node_name(b) for b in node.bases]
            if any("Seeder" in b for b in bases):
                out.append(f"  {node.name}")
    return out


def _read_pyproject_deps(root: Path) -> list[str]:
    pp = root / "pyproject.toml"
    if not pp.exists():
        return []
    try:
        with open(pp, "rb") as fh:
            data = tomllib.load(fh)
        return data.get("project", {}).get("dependencies", [])
    except Exception:
        return []


def _read_env_keys(root: Path) -> list[str]:
    env = root / ".env"
    if not env.exists():
        return []
    keys: list[str] = []
    for line in env.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            keys.append(line.split("=", 1)[0].strip())
    return keys


@mcp.tool()
def scan_project(path: str = ".") -> str:
    """Deep-scan a forge-kits project and return its full structure.

    Reads all Python source files via AST (no imports) to extract:
    - Tortoise ORM models with field names and types
    - Controllers with every registered route (METHOD + full path)
    - Pydantic schema classes grouped by file
    - Events (background/redis flags, field names)
    - Listeners and which events they handle
    - Seeders
    - pyproject.toml dependencies
    - .env variable names (values hidden)

    Use this at the start of every coding session on a forge-kits project so you
    have a complete picture of what already exists before making changes.

    Args:
        path: Path to the project root (directory containing forgeapi.toml).
              Defaults to current directory.

    Returns:
        Structured text report of the entire project.
    """
    given = Path(path).expanduser().resolve()
    toml_path = given if (given.is_file() and given.name == "forgeapi.toml") else given / "forgeapi.toml"

    if not toml_path.exists():
        return (
            f"No forgeapi.toml found at '{given}'.\n"
            "Run `forgeapi init <name>` to scaffold a project."
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
    proj = raw.get("project", {})
    auth = {**{"strategy": "jwt"}, **raw.get("auth", {})}
    base_prefix = struct["base_prefix"]

    sections: list[str] = [
        f"# Project: {proj.get('name', root.name)}  v{proj.get('version', '?')}",
        f"  auth={auth['strategy']}  prefix={base_prefix}",
        "",
    ]

    def _glob_py(dir_key: str, pattern: str) -> list[Path]:
        d = root / struct[dir_key]
        return sorted(d.rglob(pattern)) if d.exists() else []

    # Models
    model_files = _glob_py("models_dir", "*.py")
    model_files = [f for f in model_files if f.name != "__init__.py"]
    model_lines = _scan_models(model_files, root)
    sections.append("## Models")
    sections.extend(model_lines if model_lines else ["  (none found)"])
    sections.append("")

    # Controllers + routes
    ctrl_files = _glob_py("controllers_dir", "*_controller.py")
    ctrl_lines = _scan_controllers(ctrl_files, root, base_prefix)
    sections.append("## Controllers & Routes")
    sections.extend(ctrl_lines if ctrl_lines else ["  (none found)"])
    sections.append("")

    # Schemas
    schema_files = _glob_py("schemas_dir", "*.py")
    schema_files = [f for f in schema_files if f.name != "__init__.py"]
    schema_lines = _scan_schemas(schema_files, root)
    sections.append("## Schemas")
    sections.extend(schema_lines if schema_lines else ["  (none found)"])
    sections.append("")

    # Events
    event_files = _glob_py("events_dir", "*_event.py")
    event_lines = _scan_events(event_files, root)
    sections.append("## Events")
    sections.extend(event_lines if event_lines else ["  (none found)"])
    sections.append("")

    # Listeners
    listener_files = _glob_py("listeners_dir", "*_listener.py")
    listener_lines = _scan_listeners(listener_files, root)
    sections.append("## Listeners")
    sections.extend(listener_lines if listener_lines else ["  (none found)"])
    sections.append("")

    # Seeders
    seed_files = _glob_py("seeds_dir", "*_seeder.py")
    seed_lines = _scan_seeders(seed_files, root)
    sections.append("## Seeders")
    sections.extend(seed_lines if seed_lines else ["  (none found)"])
    sections.append("")

    # Dependencies
    deps = _read_pyproject_deps(root)
    sections.append("## Dependencies (pyproject.toml)")
    sections.extend(f"  {d}" for d in deps) if deps else sections.append("  (pyproject.toml not found)")
    sections.append("")

    # Env keys
    env_keys = _read_env_keys(root)
    sections.append("## .env variables (keys only)")
    sections.extend(f"  {k}" for k in env_keys) if env_keys else sections.append("  (.env not found)")

    return "\n".join(sections)


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
