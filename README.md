# ForgeAPI — Documentation

## Table of Contents

1. [Quick start](#1-quick-start)
2. [Project structure](#2-project-structure)
3. [Core](#3-core)
4. [Exceptions](#4-exceptions)
5. [Auth](#5-auth)
   - [How it works — Guards](#how-it-works--guards)
   - [CurrentUser and OptionalUser](#currentuser-and-optionaluser)
   - [Auth facade — issuing tokens](#auth-facade--issuing-tokens)
   - [Multiple guards](#multiple-guards)
   - [JWT strategy](#jwt-strategy)
   - [Cookie strategy](#cookie-strategy)
   - [Telegram strategy](#telegram-strategy)
6. [Pagination](#6-pagination)
   - [QuerySet .paginate()](#queryset-paginate)
   - [Offset pagination](#offset-pagination)
   - [Cursor pagination](#cursor-pagination)
7. [Events](#7-events)
   - [Lifecycle overview](#lifecycle-overview)
   - [Defining events](#defining-events)
   - [event_id and serialisation](#event_id-and-serialisation)
   - [@listen decorator](#listen-decorator)
   - [Dispatching](#dispatching)
   - [Background vs synchronous dispatch](#background-vs-synchronous-dispatch)
   - [Exception isolation](#exception-isolation)
   - [EventBus](#eventbus)
   - [Redis pub/sub — EventBus](#redis-pubsub--eventbus)
   - [Redis Streams — EventBus](#redis-streams--eventbus)
   - [RedisBus — cross-project bridge](#redisbus--cross-project-bridge)
   - [Testing events](#testing-events)
8. [Controllers](#8-controllers)
   - [Base pattern](#base-pattern)
   - [schema class var](#schema-class-var)
   - [Route decorator](#route-decorator)
   - [Auto-prefix and namespace](#auto-prefix-and-namespace)
9. [Schemas](#9-schemas)
   - [Base classes](#base-classes)
   - [Schema directories](#schema-directories)
   - [generate:schema](#generateschema)
10. [Policies](#10-policies)
11. [ModelMixin](#11-modelmixin)
12. [Permissions](#12-permissions)
    - [Setup](#setup)
    - [PermissionsMixin](#permissionsmixin)
    - [Dependencies](#dependencies)
    - [Role and Permission models](#role-and-permission-models)
13. [Cache](#13-cache)
    - [Basic operations](#basic-operations)
    - [Common patterns](#common-patterns)
    - [Drivers](#drivers)
    - [Configuration](#cache-configuration)
14. [Support](#14-support)
    - [Number](#number)
    - [Str](#str)
    - [Time](#time)
15. [Logger](#15-logger)
16. [Middleware](#16-middleware)
    - [CORS](#cors)
    - [Rate limiting](#rate-limiting)
    - [Request ID](#request-id)
    - [Access logging](#access-logging)
17. [Settings](#17-settings)
18. [Seeders](#18-seeders)
19. [CLI reference](#19-cli-reference)
20. [forgeapi.toml reference](#20-forgeapitoml-reference)
21. [Telescope](#21-telescope)
    - [What Telescope captures](#what-telescope-captures)
    - [WebSocket live stream](#websocket-live-stream)
    - [Sensitive data masking](#sensitive-data-masking)
    - [Recording jobs](#recording-jobs)
22. [MCP Server](#22-mcp-server)
    - [Install](#install)
    - [Global setup for Claude Code](#global-setup-for-claude-code)
    - [Per-project setup](#per-project-setup)
    - [Available tools](#available-tools)

---

## 1. Quick start

```bash
pip install forge-kits
```

### Optional dependencies

| Extra | Installs | Use when |
|---|---|---|
| `auth` | `pyjwt` | JWT or Cookie auth strategy |
| `asyncpg` | `tortoise-orm`, `asyncpg` | PostgreSQL |
| `aiosqlite` | `tortoise-orm`, `aiosqlite` | SQLite |
| `aiomysql` | `tortoise-orm`, `aiomysql` | MySQL / MariaDB |
| `db` | `tortoise-orm` | ORM only, bring your own driver |
| `redis` | `redis` | Cache Redis driver / Redis events |
| `full-asyncpg` | auth + asyncpg | PostgreSQL + JWT |
| `full-aiosqlite` | auth + aiosqlite | SQLite + JWT |
| `full-aiomysql` | auth + aiomysql | MySQL + JWT |
| `full` | auth + all three drivers | everything |
| `mcp` | `mcp` | forge-kits MCP server for AI-assisted development |

```bash
pip install forge-kits[full-asyncpg]   # PostgreSQL + JWT
pip install forge-kits[mcp]            # MCP server
pip install forge-kits[redis]          # Redis cache / events
```

```bash
forgeapi init my-project
cd my-project

forgeapi db:init && forgeapi db:makemigrations && forgeapi db:migrate
forgeapi runserver --reload
```

`forgeapi init` asks for auth strategy (jwt / cookie / telegram), DB driver (asyncpg / aiosqlite / aiomysql), and whether to generate the welcome boilerplate (User + Post + events).

---

## 2. Project structure

After `forgeapi init my-project`:

```
my-project/
  main.py                    # entry point — FastAPI app + Core(...)
  forgeapi.toml              # project config
  pyproject.toml             # dependencies — pip install -e .
  .env                       # secrets (JWT_SECRET, DB_* etc.)
  app/
    config.py                # TORTOISE_ORM dict
    controllers/             # *_controller.py files, auto-loaded by Core
    schemas/                 # Pydantic schemas
    events/                  # Event subclasses
    listeners/               # @listen(...) handlers
    policies/                # Policy classes (gate.discover)
  database/
    models/                  # Tortoise models
    migrations/              # migration files (tortoise CLI)
    seeds/                   # Seeder classes
```

**`main.py`**:

```python
from fastapi import FastAPI
from forgeapi import Core
from tortoise.contrib.fastapi import register_tortoise
from app.config import TORTOISE_ORM

app = FastAPI()

core = Core(
    app,
    auth=True,
    cors=["*"],
    rate_limit=60,
    pagination=20,
    request_id=True,
    events=True,
)

register_tortoise(app, config=TORTOISE_ORM, generate_schemas=False, add_exception_handlers=True)
```

---

## 3. Core

`Core` wires up all modules in one place.

```python
from forgeapi import Core

core = Core(
    app,
    auth=True,           # auth strategy from forgeapi.toml, or "jwt"/"cookie"/"telegram"
    cors=["*"],          # CORS origins
    rate_limit=60,       # requests per minute per IP
    pagination=20,       # default page size
    request_id=True,     # inject X-Request-ID header
    events=True,         # auto-load listeners from listeners_dir
    permissions=True,    # auto-detect PermissionsMixin model in models_dir
    logging=True,        # access log per request (default True)
    controllers=True,    # auto-discover *_controller.py files (default True)
    debug=False,         # relaxes security checks — never use in production
)
```

### Options

| Argument | Type | Default | Description |
|---|---|---|---|
| `auth` | `bool \| str` | `False` | `True` = strategy from toml; `"jwt"` / `"cookie"` / `"telegram"` = override |
| `cors` | `bool \| list[str]` | `False` | `True` = allow all; list = specific origins |
| `rate_limit` | `bool \| int` | `False` | `True` = 60 req/min; int = custom limit per IP |
| `pagination` | `bool \| int` | `False` | `True` = limits from toml; int = default_limit |
| `request_id` | `bool` | `False` | Injects `X-Request-ID` header into every response |
| `events` | `bool` | `False` | Auto-loads all `*.py` files from `listeners_dir` |
| `permissions` | `bool \| Type \| None` | `None` | `True` = auto-detect; pass model class = explicit; `None` = disabled |
| `logging` | `bool` | `True` | Logs method + path + status + duration for every request |
| `controllers` | `bool` | `True` | Auto-imports `*_controller.py` (recursive) and registers routers |
| `middleware` | `list \| None` | `None` | List of middleware classes or `(cls, kwargs)` tuples to register |
| `debug` | `bool` | `False` | Debug mode — enables Telescope. **Never use in production.** |
| `config_path` | `str` | `"forgeapi.toml"` | Path to the TOML config file |

`Core` also auto-configures `Cache` from the `[cache]` section in `forgeapi.toml` on startup.

### Accessing after setup

```python
core.auth       # → Auth facade | None
core.config     # → KitConfig (parsed forgeapi.toml)
```

### Including routers manually

```python
core.include_router(admin_router)                    # prefix: /api/v1
core.include_router(admin_router, prefix="/admin")   # prefix: /api/v1/admin
```

### Debug mode

```python
core = Core(app, auth="telegram", debug=True)
```

All debug activity is logged as `WARNING`. **Never use `debug=True` in production.**

---

## 4. Exceptions

```python
from forgeapi import ForgeAPIError, ForgeAPIConfigError, ForgeAPIImportError
```

| Class | When raised |
|---|---|
| `ForgeAPIError` | Base — all ForgeAPI errors |
| `ForgeAPIConfigError` | Misconfiguration: missing secret, unknown strategy, model not found |
| `ForgeAPIImportError` | Optional dependency not installed |

Every exception includes a `hint` field with a fix suggestion.

```python
try:
    core = Core(app, auth=True)
except ForgeAPIConfigError as e:
    print(e.hint)
```

---

## 5. Auth

Auth is based on **Guards**. A Guard combines a **strategy** (how to verify credentials) with an optional **user_model** (which Tortoise model to load from the DB).

### Step 1 — configure strategy in forgeapi.toml

```toml
[auth]
strategy           = "jwt"      # jwt | cookie | telegram
jwt_secret_env     = "JWT_SECRET"
access_ttl_minutes = 30
refresh_ttl_days   = 7
```

### Step 2 — enable in Core

```python
core = Core(app, auth=True)
```

### Step 3 — protect routes

```python
from forgeapi.auth import CurrentUser, OptionalUser

@route.get("/me")
async def me(self, user: CurrentUser):
    return {"id": user.id}

@route.get("/feed")
async def feed(self, user: OptionalUser):
    if user:
        return await personalised_feed(user.id)
    return await public_feed()
```

### What the user object contains

| Field | Type | Description |
|---|---|---|
| `user.id` | `str` | JWT `sub` claim — cast with `int(user.id)` for DB queries |
| `user.username` | `str \| None` | From token payload |
| `user.auth_method` | `str` | `"jwt"` / `"cookie"` / `"telegram"` |
| `user.extra` | `dict` | Any extra claims (`role`, `email`, etc.) |

### Auth facade — issuing tokens

```python
from forgeapi.auth import auth

access  = auth.token(user)           # access token — takes DB model instance
refresh = auth.refresh_token(user)   # refresh token — JWT only, takes DB model instance

# Decode
payload = auth.decode(token, expected_type="access")  # raises TokenExpiredError | TokenInvalidError

# Cookie strategy only
auth.set_cookie(response, {"sub": str(user.id), "username": user.username})
auth.delete_cookie(response)
```

`auth.token(user)` and `auth.refresh_token(user)` accept any model instance — they extract `id`, `username`/`email`/`name` automatically via `_build_payload`.

### Login endpoint pattern

```python
@route.post("/login")
async def login(self, payload: LoginPayload) -> dict:
    user = await User.get_or_none(email=payload.email)
    if not user or not user.verify_password(payload.password):
        raise HTTPException(401, "Invalid credentials")
    return {
        "access_token":  auth.token(user),
        "refresh_token": auth.refresh_token(user),
        "token_type":    "bearer",
    }

@route.post("/refresh")
async def refresh(self, payload: RefreshPayload) -> dict:
    try:
        data = auth.decode(payload.refresh_token, expected_type="refresh")
    except (TokenExpiredError, TokenInvalidError) as e:
        raise HTTPException(401, str(e))
    user = await User.find_or_fail(int(data["sub"]))
    return {"access_token": auth.token(user), "token_type": "bearer"}
```

### Multiple guards

```python
from forgeapi.auth.guard import Guard
from forgeapi.auth.facade import auth
from forgeapi.auth.strategies import JWTStrategy

core = Core(app, auth=False)

auth.register("api", Guard(name="api", strategy=JWTStrategy(secret_key="user-secret"), user_model=User))
auth.register("admin", Guard(name="admin", strategy=JWTStrategy(secret_key="admin-secret"), user_model=Admin))
auth.set_default("api")
```

### JWT strategy

Reads `Authorization: Bearer <token>`.

```toml
[auth]
strategy           = "jwt"
jwt_secret_env     = "JWT_SECRET"
access_ttl_minutes = 30
refresh_ttl_days   = 7
```

### Cookie strategy

Stores a signed JSON session in an `HttpOnly` cookie. Secret from `COOKIE_SECRET` env var.

```toml
[auth]
strategy        = "cookie"
cookie_name     = "session"
cookie_httponly = true
cookie_secure   = false    # true in production (HTTPS)
```

```python
from forgeapi.auth.strategies import CookieStrategy
strategy = CookieStrategy()

strategy.set_cookie(response, {"sub": str(user.id)})
strategy.delete_cookie(response)
```

### Telegram strategy

Validates `initData` from Telegram Mini App. No login endpoint needed.

```toml
[auth]
strategy = "telegram"
```

```bash
BOT_TOKEN=123456:ABC-your-token
BOT_TOKEN=123456:ABC-one,789012:DEF-two   # multiple bots, comma-separated
```

Client sends `window.Telegram.WebApp.initData` via `X-Telegram-Init-Data` header or `Authorization: tma <initData>`.

---

## 6. Pagination

Two flavors: **QuerySet `.paginate()`** (recommended), **offset** (classic), and **cursor** (stable on inserts/deletes).

### QuerySet .paginate()

The cleanest way — call `.paginate()` directly on any QuerySet:

```python
from fastapi import Request
from forgeapi.controllers import Controller, route

class PostController(Controller):
    prefix = "/posts"
    tags   = ["posts"]
    schema = PostResponse

    @route.get("/", response_model=None)
    async def index(self, request: Request):
        return await Post.all().order_by("-created_at").paginate(request, PostResponse)

    @route.get("/published", response_model=None)
    async def published(self, request: Request):
        return await Post.filter(is_published=True).paginate(request, PostResponse)
```

Query params: `?page=1&per_page=20`. Response:

```json
{
  "data": [...],
  "meta": {
    "current_page": 1,
    "per_page": 20,
    "total": 47,
    "last_page": 3,
    "from": 1,
    "to": 20
  },
  "links": {
    "prev": null,
    "next": "/posts?page=2&per_page=20"
  }
}
```

`schema` is optional — omit to get raw ORM objects.

### Offset pagination

Classic DI-based pagination:

```python
from forgeapi.pagination import Pagination

@route.get("/")
async def index(self, pagination: Pagination, request: Request):
    return await pagination.paginate(Post.all().order_by("-created_at"), PostResponse, request)
```

`pagination.page`, `pagination.limit`, `pagination.offset` are available as attributes.

### Cursor pagination

No OFFSET — stable and O(1) on large datasets:

```python
from forgeapi.pagination import CursorPagination

@route.get("/")
async def index(self, p: CursorPagination, request: Request):
    return await p.paginate(Post.all(), PostResponse, request, order_by="-id")
```

Query params: `?cursor=<token>&per_page=20`.

### Configuration

```toml
[pagination]
default_limit = 20
max_limit     = 100
```

```python
Core(app, pagination=20)   # default_limit=20
```

---

## 7. Events

Events decouple side effects (emails, notifications, cache invalidation) from business logic.

### Lifecycle overview

```
route handler
    │
    └─ await event.dispatch()
              │
              ├─ background=False → asyncio.gather(all listeners) → await → continue
              ├─ background=True  → asyncio.create_task(gather) → continue immediately
              └─ redis=True       → publish to Redis → each worker runs local listeners
```

### Defining events

```python
from forgeapi import Event

class OrderCreated(Event):
    background = True        # True = fire-and-forget
    redis      = False       # True = publish to Redis
    redis_type = "pubsub"    # "pubsub" | "stream"
    namespace  = "forgeapi:events"
    ttl: int | None = None   # Redis dedup window in seconds

    def __init__(self, order_id: int, total: float) -> None:
        self.order_id = order_id
        self.total    = total
```

| Flag | Default | Effect |
|---|---|---|
| `background` | `False` | `True` = listeners run in background task |
| `redis` | `False` | `True` = publish to Redis |
| `redis_type` | `"pubsub"` | `"pubsub"` = fan-out; `"stream"` = persistent consumer groups |
| `ttl` | `None` | Dedup window — only first worker that wins `SET NX EX {ttl}` processes it |

### event_id and serialisation

Every event automatically gets `self.event_id = str(uuid.uuid4())`. Override `to_dict()` / `from_dict()` for custom serialisation:

```python
def to_dict(self) -> dict:
    base = super().to_dict()
    base["items"] = [{"id": i.id} for i in self.items]
    return base
```

### @listen decorator

```python
from forgeapi import listen

@listen(OrderCreated)
async def send_confirmation(event: OrderCreated) -> None:
    await mailer.send(f"Order #{event.order_id} confirmed")

@listen(OrderCreated)
async def update_inventory(event: OrderCreated) -> None:
    await Inventory.decrease(order_id=event.order_id)
```

Multiple listeners run **in parallel** via `asyncio.gather`. `Core(app, events=True)` imports all files in `listeners_dir` automatically.

### Dispatching

```python
await OrderCreated(order_id=order.id, total=order.total).dispatch()
```

### Background vs synchronous dispatch

```python
# background=False — route waits for all listeners
class UserRegistered(Event):
    background = False

# background=True — response returned immediately
class OrderShipped(Event):
    background = True
```

### Exception isolation

Each listener is wrapped in try/except — one failure doesn't kill the others.

### EventBus

```python
from forgeapi import EventBus

bus = EventBus.get_instance()
bus.register(OrderCreated, my_handler)
bus.load_from_dir("app/listeners")
EventBus.reset()   # clear all listeners — use in tests
```

### Redis pub/sub — EventBus

```python
class OrderShipped(Event):
    background = True
    redis = True
    ttl = 300  # one worker per event_id per 5 minutes

    def __init__(self, order_id: int) -> None:
        self.order_id = order_id
```

Wire up in lifespan:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    bus = EventBus.get_instance()
    await bus.redis_connect("redis://localhost:6379")
    task = asyncio.create_task(bus.start_redis_subscriber())
    yield
    task.cancel()
    await bus.redis_disconnect()
```

### Redis Streams — EventBus

Persistent delivery with consumer groups — messages survive worker restarts:

```python
class OrderEvent(Event):
    background = True
    redis      = True
    redis_type = "stream"
    namespace  = "shop"      # stream key → shop:OrderEvent

    def __init__(self, order_id: int, total: float) -> None:
        self.order_id = order_id
        self.total    = total
```

Consumer:

```python
async def main():
    bus = EventBus.get_instance()
    await bus.redis_connect("redis://localhost:6379")

    @bus.on(OrderEvent)
    async def on_order(event: OrderEvent):
        await warehouse.fulfill(event.order_id)

    await bus.start_stream_subscriber(
        group="warehouse_group",
        consumer="worker_1",
        event_classes=[OrderEvent],
    )
```

| | `redis_type="pubsub"` | `redis_type="stream"` |
|---|---|---|
| Persistence | None | Stored until all groups ACK |
| Delivery | All subscribers simultaneously | Each group independently |
| Offline workers | Miss messages | Catch up on reconnect |
| Dedup | `ttl` class var | Not built-in |

### RedisBus — cross-project bridge

Communication between **different projects** sharing a Redis URL:

```python
from forgeapi import RedisBus

bus = RedisBus("redis://localhost:6379", namespace="shop")

@bus.on("order:created")
async def handle(data: dict) -> None:
    await telegram.send(f"Order #{data['id']}")

await bus.emit("order:created", {"id": 42, "total": 99.0})
```

Lifecycle with FastAPI:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    async with bus:
        yield
```

### Testing events

```python
import pytest
from forgeapi import EventBus

@pytest.fixture(autouse=True)
def reset_bus():
    EventBus.reset()
    yield
    EventBus.reset()
```

---

## 8. Controllers

Controllers group routes. `Core` auto-discovers all `*_controller.py` files in `controllers_dir` (recursively) and registers their routers under `base_prefix`.

### Base pattern

```python
from fastapi import Request
from forgeapi.controllers import Controller, route
from forgeapi.auth import CurrentUser
from database.models.post import Post
from app.schemas.post import PostResponse, PostCreatePayload, PostUpdatePayload


class PostController(Controller):
    prefix = "/posts"
    tags   = ["posts"]
    schema = PostResponse   # auto response_model (see below)

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
```

### schema class var

Set `schema` on the controller class to auto-inject `response_model` on every route — no need to repeat it on each decorator:

```python
class PostController(Controller):
    schema = PostResponse   # applied automatically to all routes

    @route.get("/")           # → response_model=PostResponse (auto)
    async def index(self): ...

    @route.get("/", response_model=None)   # override: disable for this route
    async def index(self, request: Request):
        return await Post.all().paginate(request, PostResponse)

    @route.delete("/{id}", status_code=204)  # skipped: no response body on 204
    async def destroy(self, id: int): ...
```

Rules:
- Routes with `status_code=204` are skipped (no body)
- Routes with an explicit `response_model=...` keep their own value
- All other routes get `response_model=schema`

### Route decorator

```python
@route.get("/")
@route.post("/", status_code=201)
@route.put("/{id}")
@route.patch("/{id}")
@route.delete("/{id}", status_code=204)

# explicit form — multiple methods
@route("/", methods=["GET", "POST"])
```

All kwargs are forwarded to FastAPI (`response_model`, `summary`, `dependencies`, etc.).

### Auto-prefix and namespace

If `prefix` is not set, it is derived from the class name:

| Class | Auto prefix |
|---|---|
| `PostController` | `/posts` |
| `AdminUserController` | `/admin/users` |
| `SuperAdminOrderController` | `/super/admin/orders` |

Final URL = `base_prefix` + `controller.prefix` + `route path`

```bash
forgeapi make:controller Post          # controllers/post_controller.py
forgeapi make:controller AdminUser     # controllers/admin/user_controller.py
```

---

## 9. Schemas

### Base classes

```python
from forgeapi import BaseSchema, BaseCreateSchema, BaseUpdateSchema
```

**`BaseSchema`** — response schemas. Has `id`, `created_at`, `updated_at`. `from_attributes=True` reads directly from Tortoise instances.

```python
class PostResponse(BaseSchema):
    title: str
    body:  str

PostResponse.model_validate(post)
```

**`BaseCreateSchema`** — POST payloads. Plain `BaseModel` subclass.

```python
class PostCreatePayload(BaseCreateSchema):
    title: str
    body:  str
```

**`BaseUpdateSchema`** — PATCH payloads. Enforces that every field is `Optional` at class definition time.

```python
class PostUpdatePayload(BaseUpdateSchema):
    title: str | None = None
    body:  str | None = None
```

### Schema directories

```
schemas/
  payload/
    post.py       # PostCreatePayload, PostUpdatePayload
  response/
    post.py       # PostResponse
```

### generate:schema

```bash
forgeapi generate:schema Post --payload             # Create + Update payloads
forgeapi generate:schema Post --response            # PostResponse
forgeapi generate:schema Post --payload --response  # both
forgeapi generate:schema Post --payload -crud       # all four classes
```

---

## 10. Policies

Policies encapsulate authorization logic per resource.

### Defining a policy

```python
# app/policies/post_policy.py
from forgeapi.policies import Policy
from forgeapi import gate

@gate.policy(Post)
class PostPolicy(Policy):
    async def before(self, user, action: str) -> bool | None:
        if await user.has_role("admin"):
            return True   # admins bypass all checks
        return None       # continue to action method

    async def view(self, user, post) -> bool:
        return True

    async def create(self, user) -> bool:
        return user is not None

    async def update(self, user, post) -> bool:
        return post.author_id == int(user.id)

    async def delete(self, user, post) -> bool:
        return post.author_id == int(user.id)
```

`@gate.policy(Post)` registers the class — no separate step needed.

### Using in controllers

```python
from forgeapi import gate

@route.patch("/{id}")
async def update(self, id: int, payload: PostUpdatePayload, user: CurrentUser):
    post = await Post.find_or_fail(id)
    await gate.authorize(user, "update", post)   # raises HTTP 403 if denied
    return await post.update_from(payload)
```

### Checking without raising

```python
if await gate.allows(user, "delete", post): ...
if await gate.denies(user, "update", post): ...
```

### Auto-discovery

```python
gate.discover("app/policies")   # imports all *_policy.py files
```

### Gate methods

| Method | Description |
|---|---|
| `gate.authorize(user, action, subject)` | Raise `HTTP 403` if denied |
| `gate.allows(user, action, subject)` | Return `bool` |
| `gate.denies(user, action, subject)` | Inverse of `allows` |
| `gate.policy(ModelClass)` | Decorator — register policy for a model |
| `gate.register(ModelClass, PolicyClass)` | Explicit registration |
| `gate.discover(dir)` | Auto-import all `*_policy.py` files |

`subject` can be a model **instance** (update/delete) or a model **class** (create).

---

## 11. ModelMixin

`ModelMixin` adds ORM shortcuts and enables `.paginate()` on every QuerySet. Mix it alongside `tortoise.Model`:

```python
from tortoise import fields, Model
from forgeapi import ModelMixin

class Post(ModelMixin, Model):
    id           = fields.IntField(pk=True)
    title        = fields.CharField(max_length=255)
    body         = fields.TextField()
    is_published = fields.BooleanField(default=False)
    author_id    = fields.IntField()
    created_at   = fields.DatetimeField(auto_now_add=True)
    updated_at   = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "posts"

    @classmethod
    def published(cls):
        return cls.filter(is_published=True)

    @classmethod
    def by_author(cls, author_id: int):
        return cls.filter(author_id=author_id)
```

### Methods

**`find_or_fail(id, field="id")`** — get by field or raise HTTP 404:

```python
post = await Post.find_or_fail(42)
post = await Post.find_or_fail("my-slug", field="slug")
```

**`create_from(payload, **extra)`** — create from a Pydantic schema:

```python
post = await Post.create_from(payload)
post = await Post.create_from(payload, author_id=int(user.id))
```

`None` values are excluded — no accidental `null` writes.

**`update_from(payload, **extra)`** — partial update from schema, then `save()`:

```python
await post.update_from(payload)
await post.update_from(payload, updated_by=int(user.id))
```

### QuerySet .paginate()

`ModelMixin` injects `ForgeManager` automatically so `.paginate()` is available on every QuerySet chain:

```python
# Full paginated response
result = await Post.all().order_by("-created_at").paginate(request, PostResponse)

# With filters
result = await Post.published().paginate(request, PostResponse)
result = await Post.by_author(user_id).order_by("-created_at").paginate(request, PostResponse)

# Without schema — returns raw ORM objects
result = await Post.all().paginate(request)
```

### Before vs after ModelMixin

```python
# Before
data = payload.model_dump(exclude_none=True)
post = await Post.create(**data, author_id=int(user.id))

# After
post = await Post.create_from(payload, author_id=int(user.id))

# Before
for k, v in payload.model_dump(exclude_none=True).items():
    setattr(post, k, v)
await post.save()

# After
await post.update_from(payload)
```

---

## 12. Permissions

Spatie-style roles and permissions using polymorphic pivot tables.

### How it works

Two shared tables store all assignments:

```
model_has_roles             model_has_permissions
──────────────────          ──────────────────────
model_type = "user"         model_type = "user"
model_id   = 42             model_id   = 42
role_id    = 1              permission_id = 3
```

`model_type` is the lowercase class name. Adding permissions to a new model requires zero new migrations.

### Setup

**1. Add `PermissionsMixin` to your model:**

```python
from tortoise import fields
from forgeapi.permissions import PermissionsMixin

class User(PermissionsMixin):
    id       = fields.IntField(pk=True)
    username = fields.CharField(max_length=150, unique=True)
    email    = fields.CharField(max_length=255, unique=True)

    class Meta:
        table = "users"
```

**2. Add permissions models to TORTOISE_ORM:**

```python
TORTOISE_ORM = {
    "apps": {
        "models": {
            "models": ["database.models", "forgeapi.permissions.models"],
            ...
        },
    },
}
```

**3. Register in Core:**

```python
core = Core(app, auth=True, permissions=True)    # auto-detect
core = Core(app, auth=True, permissions=User)    # explicit
```

**4. Run migrations:**

```bash
forgeapi db:makemigrations && forgeapi db:migrate
```

### PermissionsMixin

```python
# Checking
await user.can("edit:posts")                        # True if has any (direct or via role)
await user.can("edit:posts", "admin")               # OR logic
await user.cannot("delete:users")
await user.has_all_permissions("read", "write")     # AND logic
await user.has_role("admin")
await user.has_all_roles("admin", "editor")

# Granting / revoking
await user.give_permission("edit:posts", "delete:posts")
await user.revoke_permission("delete:posts")
await user.assign_role("admin", "editor")
await user.remove_role("editor")

# Listing
await user.get_all_permissions()   # → ["edit:posts", ...]
await user.get_role_names()        # → ["admin", "editor"]
```

### Dependencies

```python
from forgeapi.permissions import require_permission, require_role

@route.delete("/{id}")
async def destroy(self, id: int, user=require_permission("delete:posts")): ...

@route.post("/")
async def create(self, payload, user=require_permission("create:posts", "admin")): ...   # OR

@route.get("/admin/stats")
async def stats(self, user=require_role("admin")): ...
```

Both dependencies also check `db_user.is_active` when the field exists — inactive users receive `401`.

### Role and Permission models

```python
from forgeapi.permissions.models import Role, Permission

role = await Role.find_or_create("editor")
await role.give_permission("edit:posts", "read:posts")
await role.has_permission("edit:posts")   # → bool

# Filtering by role
users = await (await User.with_role("admin"))
users = await (await User.without_role("admin"))
```

---

## 13. Cache

Async key-value cache. Two drivers: **memory** (default, no dependencies) and **redis** (persistent, shared across workers).

`Core` auto-configures `Cache` from `forgeapi.toml` on startup.

```python
from forgeapi import Cache
```

### Basic operations

```python
await Cache.set("key", value, ttl=60)        # store for 60 seconds
await Cache.get("key")                        # → value or None
await Cache.get("key", default="fallback")
await Cache.has("key")                        # → bool
await Cache.missing("key")                    # → bool (inverse)
await Cache.forget("key")                     # delete → bool
await Cache.flush()                           # clear all
await Cache.forever("key", value)             # store without TTL
```

### Common patterns

**`remember()`** — get or compute and store:

```python
posts = await Cache.remember(
    "posts:popular",
    fn=lambda: Post.filter(is_published=True).limit(10),
    ttl=300,
)

# async fn works too
async def fetch_stats():
    return await compute_heavy_stats()

stats = await Cache.remember("stats:global", fn=fetch_stats, ttl=3600)
```

**`pull()`** — get and immediately delete (one-time tokens):

```python
token = await Cache.pull(f"reset:token:{user_id}")
if token != submitted_token:
    raise HTTPException(400, "Invalid token")
```

**Counters:**

```python
await Cache.increment("views:post:42")         # → int
await Cache.increment("views:post:42", amount=5)
await Cache.decrement("stock:item:5")
```

**Use in a controller:**

```python
@route.get("/popular", response_model=None)
async def popular(self, request: Request):
    cached = await Cache.get("posts:popular")
    if cached:
        return cached
    result = await Post.filter(is_published=True).paginate(request, PostResponse)
    await Cache.set("posts:popular", result, ttl=60)
    return result
```

### Drivers

| Driver | When to use |
|---|---|
| `memory` | Single process, development, testing. Resets on restart. |
| `redis` | Multiple workers, production. Requires `pip install forge-kits[redis]` |

### Cache configuration

```toml
[cache]
driver    = "memory"                    # "memory" | "redis"
prefix    = ""                          # key prefix, e.g. "myapp:"
ttl       = null                        # default TTL in seconds (null = no expiry)
redis_url = "redis://localhost:6379/0"  # used when driver = "redis"
```

Programmatic setup (without Core):

```python
from forgeapi import Cache

Cache.configure(driver="redis", prefix="myapp:", ttl=3600, redis_url="redis://localhost:6379/1")
```

---

## 14. Support

Utility helpers for formatting numbers, strings, and datetimes.

```python
from forgeapi import Number, Str, Time
```

### Number

```python
Number.format(1234567.89)             # "1,234,567.89"
Number.format(1234.5, decimals=0)     # "1,235"
Number.format(1234.5, thousands=".", decimal=",")  # "1.234,50" (EU style)

Number.currency(99.9)                 # "99.90"
Number.currency(100.00044443)         # "100.00"  — messy float, clean output
Number.currency(1234.5)               # "1,234.50"

Number.file_size(1024)                # "1.0 KB"
Number.file_size(1048576)             # "1.0 MB"
Number.file_size(1073741824)          # "1.0 GB"
Number.file_size(1024, unit="MB")     # "0.0 MB"  — forced unit

Number.percent(0.754)                 # "75.4%"
Number.percent(0.5, decimals=0)       # "50%"

Number.abbreviate(1500000)            # "1.5M"
Number.abbreviate(2300)               # "2.3K"
Number.abbreviate(500)                # "500"

Number.clamp(150, 0, 100)             # 100
Number.clamp(-5, 0, 100)              # 0
```

### Str

```python
Str.limit("Hello world", 5)           # "Hello..."
Str.limit("Hello world", 5, " →")    # "Hello →"

Str.slug("Hello World!")              # "hello-world"
Str.slug("  Café & Bistro  ")        # "café-bistro"

Str.random(16)                        # "Xk9mR2pLqT8vNcYw"
Str.random(8, alphabet="0123456789") # "48291037"

Str.title("hello world")              # "Hello World"
Str.snake("HelloWorld")               # "hello_world"
Str.snake("hello-world")              # "hello_world"
Str.camel("hello_world")              # "helloWorld"
Str.pascal("hello_world")             # "HelloWorld"

Str.truncate_words("one two three four", 2)  # "one two..."

Str.strip_tags("<b>Hello</b> <i>world</i>")  # "Hello world"

Str.mask("1234567890", start=4)       # "1234******"
Str.mask("1234567890", char="•", start=0, length=4)  # "••••567890"

Str.contains("Hello World", "world", case_sensitive=False)  # True
Str.starts_with("Hello", "He")        # True
Str.ends_with("Hello", "lo")          # True
```

### Time

```python
Time.now()                            # datetime UTC
Time.now("Europe/Kyiv")               # datetime in timezone

Time.parse("2025-07-14")              # → datetime
Time.parse("2025-07-14T12:00:00Z")    # → datetime
Time.parse(1720958400)                # → datetime from Unix timestamp

Time.format(dt)                       # "2025-07-14 12:00:00"
Time.format(dt, "%d/%m/%Y")           # "14/07/2025"

Time.to_timezone(dt, "US/Eastern")    # convert timezone
Time.to_timezone(dt, "Europe/Kyiv")

Time.timestamp(dt)                    # → int (Unix timestamp)

Time.add(dt, days=1, hours=3)         # → datetime
Time.subtract(dt, days=7)             # → datetime
Time.diff_in_days(dt1, dt2)           # → int (absolute)
Time.diff_in_seconds(dt1, dt2)        # → int (absolute)

Time.human(dt)                        # "just now" / "5 minutes ago" / "in 3 hours"
Time.human(dt, relative_to=other_dt)  # relative to a specific point

Time.is_past(dt)                      # → bool
Time.is_future(dt)                    # → bool

Time.start_of_day(dt)                 # 00:00:00.000000
Time.end_of_day(dt)                   # 23:59:59.999999
```

---

## 15. Logger

forge-kits includes a structured logger so you don't need to call `logging.getLogger(__name__)` everywhere.

```python
from forgeapi import Log

Log.info("Order created", order_id=order.id, user_id=user.id)
Log.warning("Payment retry", order_id=order.id, attempt=3)
Log.error("Stripe failed", order_id=order.id, reason=str(e))
```

Context is appended as `key=value` pairs:

```
INFO  Order created | order_id=42  user_id=7
ERROR Stripe failed | order_id=42  reason='Card declined'
```

### Named channels

```python
auth_log = Log.channel("auth")
auth_log.debug("Token decoded", user_id=42)
```

### Methods

| Method | Level |
|---|---|
| `Log.debug(msg, **ctx)` | `DEBUG` |
| `Log.info(msg, **ctx)` | `INFO` |
| `Log.warning(msg, **ctx)` | `WARNING` |
| `Log.error(msg, **ctx)` | `ERROR` |
| `Log.critical(msg, **ctx)` | `CRITICAL` |
| `Log.channel(name)` | Returns child `Logger` |

`Log` wraps Python's standard `logging` — existing handlers keep working unchanged.

---

## 16. Middleware

Two extension points: **global middleware** wraps every request, **guards** scope to a route or controller.

### Custom global middleware

```python
from forgeapi import Middleware
from fastapi import Request, Response

class TimingMiddleware(Middleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        import time
        start = time.perf_counter()
        response = await call_next(request)
        response.headers["X-Process-Time"] = f"{time.perf_counter() - start:.3f}s"
        return response

core = Core(app, middleware=[TimingMiddleware])
core.use(TimingMiddleware)
core.use(TenantMiddleware, default_tenant="acme")
```

### Guards — per-route / per-controller

```python
from forgeapi import Guard
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
@route.delete("/{id}", dependencies=[Depends(ApiKeyGuard())])
async def destroy(self, id: int): ...
```

Per-controller:

```python
class AdminController(Controller):
    guards = [ApiKeyGuard("X-Admin-Key")]
```

Guards can use FastAPI dependencies directly in `handle`:

```python
from forgeapi.auth import CurrentUser

class ActiveUserGuard(Guard):
    async def handle(self, user: CurrentUser) -> None:
        if not user.is_active:
            raise HTTPException(403, "Account disabled")
```

### Built-in middleware

| Argument | Default | Description |
|---|---|---|
| `cors` | `False` | `["*"]` or list of origins |
| `rate_limit` | `False` | `True` = 60 req/min; int = custom limit |
| `request_id` | `False` | Injects `X-Request-ID` header |
| `logging` | `True` | Logs method, path, status, duration |

#### CORS

```python
Core(app, cors=["*"])
Core(app, cors=["https://example.com", "https://app.example.com"])
```

#### Rate limiting

Sliding window per IP. Returns `429` with `Retry-After` header.

```python
Core(app, rate_limit=True)   # 60 req/min
Core(app, rate_limit=200)
```

#### Request ID

```python
Core(app, request_id=True)
# Access via: request.state.request_id
```

---

## 17. Settings

`BaseAppSettings` wraps `pydantic-settings` with `.env` file loading:

```python
from forgeapi.settings import BaseAppSettings

class Settings(BaseAppSettings):
    database_url: str
    redis_url: str | None = None
    jwt_secret: str
    debug: bool = False

settings = Settings()   # reads .env automatically
```

Sensitive field masking — fields containing `password`, `secret`, `token`, `key`, `auth`, `credential` show `***` in `repr`:

```python
>>> print(settings)
Settings(database_url='postgresql://...', jwt_secret='***', debug=True)
```

---

## 18. Seeders

Seeders populate the database with initial or test data.

```bash
forgeapi make:seed User
# → database/seeds/user_seeder.py
```

```python
from forgeapi.database import Seeder
from database.models import User

class UserSeeder(Seeder):
    async def run(self) -> None:
        await User.get_or_create(
            username="admin",
            defaults={"email": "admin@example.com", "is_active": True},
        )
```

Running:

```bash
forgeapi db:seed              # run all seeders
forgeapi db:seed User         # run UserSeeder only
forgeapi db:seed User Post    # run in order
```

`db:seed` wraps each seeder in a transaction — rollback on error.

---

## 19. CLI reference

```bash
forgeapi --help
forgeapi make:controller -h
```

### Project scaffolding

```bash
forgeapi init my-project
```

### Code generation

```bash
forgeapi make:controller Post          # controllers/post_controller.py
forgeapi make:controller AdminUser     # controllers/admin/user_controller.py
forgeapi make:controller Post --ms     # + model + schema stubs
forgeapi make:model Post
forgeapi make:model Post -cs           # + controller + schema
forgeapi make:event OrderShipped       # app/events/order_shipped_event.py
forgeapi make:listener OrderShipped    # app/listeners/order_shipped_listener.py
forgeapi make:seed User                # database/seeds/user_seeder.py
forgeapi make:schema Post              # stub schemas (3 classes with pass)
```

### Typed schema generation (from existing model)

```bash
forgeapi generate:schema Post --payload             # Create + Update payloads
forgeapi generate:schema Post --response            # PostResponse
forgeapi generate:schema Post --payload --response  # both
forgeapi generate:schema Post --payload -crud       # all four incl. DeletePayload
forgeapi generate:schema Post --payload --cu        # Create + Update only
```

### DB commands

> Never run `aerich` directly — always use `forgeapi db:*`

```bash
forgeapi db:init
forgeapi db:makemigrations
forgeapi db:makemigrations -n add_email_field
forgeapi db:migrate
forgeapi db:downgrade
forgeapi db:history
forgeapi db:seed
forgeapi db:fresh             # TRUNCATE all tables (asks confirmation)
forgeapi db:fresh --force     # DROP all tables (irreversible)
```

### Dev server

> Never use `uvicorn` directly — always use `forgeapi runserver`

```bash
forgeapi runserver
forgeapi runserver --reload
forgeapi runserver --port 9000 --host 0.0.0.0 --reload
```

### Inspection

```bash
forgeapi routers   # list all registered routes (METHOD, PATH, HANDLER)
forgeapi models    # list all Tortoise model classes, tables, and fields
```

---

## 20. forgeapi.toml reference

```toml
[project]
name    = "my-app"
version = "0.1.0"

[structure]
models_dir      = "database/models"
controllers_dir = "app/controllers"
schemas_dir     = "app/schemas"
events_dir      = "app/events"
listeners_dir   = "app/listeners"
seeds_dir       = "database/seeds"
base_prefix     = "/api/v1"

[auth]
strategy           = "jwt"          # jwt | cookie | telegram
jwt_secret_env     = "JWT_SECRET"   # name of env var holding the secret
access_ttl_minutes = 30
refresh_ttl_days   = 7
cookie_name        = "session"      # cookie strategy only
cookie_httponly    = true
cookie_secure      = false          # true in production (HTTPS)

[pagination]
default_limit = 20
max_limit     = 100

[cache]
driver    = "memory"                    # "memory" | "redis"
prefix    = ""                          # key prefix applied to all keys
ttl       = null                        # default TTL in seconds (null = no expiry)
redis_url = "redis://localhost:6379/0"  # used when driver = "redis"
```

All fields are optional — `Core` works without a config file using the defaults above.

---

## 21. Telescope

Debug-only request inspector activated by `Core(debug=True)`. **Never use in production.**

```python
core = Core(app, debug=True)
```

Captures per request: SQL queries, log output, dispatched events, custom jobs. Up to **200** entries in a circular buffer.

### What Telescope captures

| Field | Description |
|---|---|
| `method`, `path`, `status` | HTTP basics |
| `headers` | All headers — sensitive ones replaced with `"***"` |
| `payload` | Request body — sensitive fields masked |
| `response_body` | Response body — same masking, capped at 64 KB |
| `duration_ms` | Handler time |
| `queries` | SQL queries: text, params, duration, source location |
| `logs` | All `logging` calls during the request |
| `events` | Events dispatched during the request |
| `jobs` | Custom jobs recorded via `record_job()` |

### WebSocket live stream

Connect to `ws://<host>/_forge/telescope/ws`:

| Direction | Message |
|---|---|
| Server → Client | `{"type": "init", "data": [...]}` — all current entries on connect |
| Server → Client | `{"type": "entry", "data": {...}}` — after each request |
| Client → Server | `{"type": "clear"}` — clear the store |

### Sensitive data masking

Headers `Authorization`, `Cookie`, `X-API-Key`, `X-Telegram-Init-Data` → `"***"`

Body fields containing: `password`, `secret`, `token`, `key`, `auth`, `credential`, `access_token`, `refresh_token` → `"***"`

### Recording jobs

```python
from forgeapi.telescope import record_job

record_job("ProcessPayment", status="done", duration_ms=45.2)
record_job("SendEmail", status="failed", error=str(exc))
```

No-op when called outside a Telescope request context.

---

## 22. MCP Server

forge-kits ships an MCP server that gives AI assistants (Claude Code, Cursor, etc.) direct access to API docs, code generation tools, and project structure scanning — without reading source files.

### Install

```bash
pip install forge-kits[mcp]
```

This installs `forgeapi-mcp` as a CLI entry point.

---

### Quick setup via CLI

The easiest way — no JSON editing required:

```bash
# Per-project — adds to .mcp.json in the current directory
claude mcp add forge-kits forgeapi-mcp

# Global — adds to ~/.claude/settings.json, available in all projects
claude mcp add forge-kits forgeapi-mcp --scope global
```

---

### Global setup for Claude Code (manual)

Install once and use across **all your projects**. Edit the global Claude Code settings file:

**macOS / Linux:**
```
~/.claude/settings.json
```

**Windows:**
```
C:\Users\<your-username>\.claude\settings.json
```

Add the MCP server:

```json
{
  "mcpServers": {
    "forge-kits": {
      "command": "forgeapi-mcp"
    }
  }
}
```

After saving, restart Claude Code. The tools are now available in every project.

---

### Per-project setup

Useful when different projects use different versions of forge-kits, or when you want to use a virtualenv-specific install.

Create `.mcp.json` in your **project root** (can be committed to the repo):

```json
{
  "mcpServers": {
    "forge-kits": {
      "command": "forgeapi-mcp"
    }
  }
}
```

If `forgeapi-mcp` is installed in a virtualenv, point to it directly:

**macOS / Linux:**
```json
{
  "mcpServers": {
    "forge-kits": {
      "command": "/path/to/project/.venv/bin/forgeapi-mcp"
    }
  }
}
```

**Windows:**
```json
{
  "mcpServers": {
    "forge-kits": {
      "command": "C:\\path\\to\\project\\.venv\\Scripts\\forgeapi-mcp.exe"
    }
  }
}
```

> **Priority:** per-project `.mcp.json` takes precedence over the global `~/.claude/settings.json` when both exist.

---

### Available tools

| Tool | Description |
|---|---|
| `get_docs(topic)` | Full API reference for a topic |
| `get_example(pattern)` | Complete working code for a pattern |
| `generate_controller(name, routes)` | Generate a `Controller` class |
| `generate_event(name, fields)` | Generate an `Event` class + listener |
| `generate_schema(name, fields, mode)` | Generate Pydantic schemas |
| `scan_project(path)` | Deep AST scan: models, controllers, schemas, events, listeners, seeders, deps |
| `project_info(path)` | Read `forgeapi.toml` and list project files |

#### get_docs topics

| Topic | Content |
|---|---|
| `cheatsheet` | Controller + queries + auth + events quick reference |
| `workflow` | CLI rules — which commands to use and which to avoid |
| `core` | Core constructor, options, startup sequence |
| `controllers` | Controller, @route, schema class var, auto-prefix |
| `events` | EventBus, Redis pub/sub, Streams, RedisBus |
| `auth` | Guards, CurrentUser, strategies, token operations |
| `permissions` | PermissionsMixin, require_permission, roles |
| `policies` | Policy, Gate, authorize, allows, discover |
| `pagination` | QuerySet .paginate(), offset, cursor, configuration |
| `schemas` | BaseSchema, BaseCreateSchema, BaseUpdateSchema |
| `middleware` | Middleware, Guard, built-in middleware |
| `cli` | All CLI commands reference |
| `config` | forgeapi.toml full reference |
| `models` | ModelMixin, Tortoise field types, relationships |
| `cache` | Cache facade, drivers, remember/pull/increment |
| `support` | Number, Str, Time helpers |
| `tortoise` | Basic CRUD, filter, order, async gather |
| `tortoise_advanced` | Q objects, prefetch_related, transactions, raw SQL |

#### get_example patterns

| Pattern | Content |
|---|---|
| `crud_controller` | Full CRUD with ModelMixin + schema class var |
| `jwt_auth` | Login, refresh, protected routes |
| `redis_event` | Redis pub/sub fan-out event |
| `stream_event` | Redis Streams consumer |
| `rbac` | Full RBAC — model, seeder, protected routes |
| `pagination` | QuerySet .paginate() with filters |
| `guard` | API key, active-user, admin guards |
| `cache` | remember, pull, counters in a controller |

#### generate_controller

```
generate_controller("Post", ["GET /", "POST /", "GET /{id}", "PATCH /{id}", "DELETE /{id}"])
```

#### scan_project

```
scan_project(".")
```

Returns a structured report of all models, controllers, schemas, events, listeners, seeders, pyproject.toml dependencies, and .env keys (values hidden). Call this at the start of every session on a forge-kits project.
