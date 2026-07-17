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
20. [Configuration reference (config/)](#20-configuration-reference-config)
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
  main.py                    # entry point — FastAPI app + Core(app)
  .env                       # secrets (JWT_SECRET, DB_* etc.)
  config/                    # Laravel-style config directory (see §20)
    project.py               # name, debug, extra providers
    structure.py             # directory layout + base_prefix
    http.py                  # cors, rate_limit, request_id, access_log, middleware
    auth.py                  # named guards (jwt / cookie / telegram)
    pagination.py            # default_limit, max_limit
    database.py              # TORTOISE_ORM dict lives here
  app/
    controllers/             # *_controller.py files, auto-loaded by Core
    schemas/                 # Pydantic schemas
    events/                  # Event subclasses
    listeners/               # @listen(...) handlers
    policies/                # Policy classes, auto-discovered
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
from config.database import TORTOISE_ORM

app = FastAPI()

core = Core(app)   # everything is wired from config/

register_tortoise(app, config=TORTOISE_ORM, generate_schemas=False, add_exception_handlers=True)
```

---

## 3. Core

**`Core(app)` takes only the app.** Everything else is config-driven —
convention over configuration. `Core` is a thin orchestrator: each module
ships a `Provider` with a `register()` phase (module wiring) and a `boot()`
phase (user-code discovery); `Core` collects them, runs all `register()`s,
then all `boot()`s.

```python
from forgeapi import Core

core = Core(app)
```

### What boots when

| Module | Activated by |
|---|---|
| Middleware stack | `config/http.py` (`cors`, `rate_limit`, `request_id`, `access_log`, `middleware`) |
| Auth guards | `config/auth.py` exists |
| Controllers | `controllers_dir` exists — all `*_controller.py` imported recursively |
| Event listeners | `listeners_dir` exists — all files imported |
| Policies | `policies_dir` exists — all `*_policy.py` imported |
| Permissions | a model in `models_dir` inherits `PermissionsMixin` (no config needed) |
| Telescope | `"debug": True` in `config/project.py` — **never in production** |
| Pagination, Cache | always configured (from their sections or defaults) |
| Custom providers | `"providers"` list in `config/project.py` |

`Core(app)` with no config files never raises — zero-config is a supported
starting point.

### Custom providers

```python
# config/project.py
config = {"providers": ["app.providers.MetricsProvider"]}
```

```python
from forgeapi import Provider

class MetricsProvider(Provider):
    def register(self) -> None: ...   # module wiring — must not import user code
    def boot(self) -> None: ...       # runs after all register()s
```

### Accessing after setup

```python
core.auth       # → Auth facade | None
core.config     # → KitConfig (validated config/ sections)
core.providers  # → list of active Provider instances
```

### Including routers manually

```python
core.include_router(admin_router)                    # prefix: /api/v1
core.include_router(admin_router, prefix="/admin")   # prefix: /api/v1/admin
```

### Debug mode

```python
# config/project.py
from forgeapi import env
config = {"debug": env("APP_DEBUG", False)}
```

Debug mode enables Telescope; all debug activity is logged as `WARNING`.
**Never enable in production.**

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
    core = Core(app)
except ForgeAPIConfigError as e:
    print(e.hint)
```

Auth has its own domain-exception hierarchy (`ForgeAPIAuthError` subclasses:
`TokenExpiredError`, `TokenInvalidError`, `SessionExpiredError`,
`SessionInvalidError`, `UserNotFoundError`). Strategies raise only these —
`Guard.authenticate` is the single point translating them to HTTP 401 (see §5).

---

## 5. Auth

Auth is based on **Guards**. A Guard combines a **strategy** (how to verify credentials) with an optional **user model** (which Tortoise model to load from the DB).

```
Auth (facade)   — guard registry + strategy factories, pure delegation
 └─ Guard       — the only layer that speaks HTTP (401) and touches the DB
     └─ AuthStrategy — pure domain: extract/verify credentials, issue tokens
```

### Step 1 — define guards in config/auth.py

Auth boots automatically when `config/auth.py` exists — nothing to pass to `Core`.

```python
# config/auth.py
from forgeapi import env

config = {
    "default": "api",
    "guards": {
        "api": {
            "strategy": "jwt",              # jwt | cookie | telegram | custom
            "secret": env("JWT_SECRET"),
            "access_ttl": 30,               # minutes
            "refresh_ttl": 7,               # days
            "model": "database.models.user.User",   # optional — load user from DB
        },
    },
}
```

`strategy` picks the credential mechanism; the remaining keys are passed to
the strategy's `from_config()` (see per-strategy tables below). `model` is a
dotted path to a Tortoise model — when set, `CurrentUser` resolves to a real
DB instance (and a valid token whose user is gone from the DB is a 401).

### Step 2 — protect routes

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

### Error semantics (uniform across strategies)

- credentials **absent** → 401 for `CurrentUser`, `None` for `OptionalUser`
- credentials **present but invalid** (expired / bad signature / user gone
  from the DB) → **401 always**, even for `OptionalUser`
- every 401 carries `WWW-Authenticate: Bearer error="<code>"` with a
  machine-readable code: `token_expired`, `token_invalid`, `session_expired`,
  `session_invalid`, `user_not_found`, `missing_credentials`

### What the user object contains

With `"model"` configured, the dependency returns your **Tortoise model
instance** loaded from the DB — all its fields and methods are available.

Without `"model"`, it returns a lightweight `AuthUser` built from the token
payload:

| Field | Type | Description |
|---|---|---|
| `user.id` | `str \| int` | JWT `sub` claim — cast with `int(user.id)` for DB queries |
| `user.username` | `str \| None` | From token payload |
| `user.auth_method` | `str` | `"jwt"` / `"cookie"` / `"telegram"` |
| `user.extra` | `dict` | Any extra claims (`role`, `email`, etc.) |

### Token claims — auth_claims()

Define `auth_claims()` on the user model to control what goes into tokens
(`sub` is auto-filled from `user.id`):

```python
class User(ModelMixin, Model):
    def auth_claims(self) -> dict:
        return {"username": self.username, "role": self.role}
```

### Auth facade — issuing tokens

```python
from forgeapi.auth import auth

access  = auth.token(user)           # access token — takes DB model instance
refresh = auth.refresh_token(user)   # refresh token — RefreshCapable strategies (jwt)

# Decode
payload = auth.decode(token, expected_type="access")  # raises TokenExpiredError | TokenInvalidError

# SessionIssuer strategies (cookie) only
auth.set_cookie(response, {"sub": str(user.id), "username": user.username})
auth.delete_cookie(response)
```

`auth.token(user)` accepts any model instance — `sub` is auto-filled from
`user.id`, the rest comes from the model's `auth_claims()` hook (see above).

Capabilities are protocols (`forgeapi.auth.contracts`): `TokenIssuer`,
`RefreshCapable`, `SessionIssuer`. The facade dispatches on
`isinstance(strategy, Protocol)` — a custom strategy that implements a
protocol gets `token()` / `decode()` / cookie helpers for free.

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

Define several named guards in `config/auth.py`; each gets its own strategy,
secret, and user model:

```python
# config/auth.py
config = {
    "default": "api",
    "guards": {
        "api":   {"strategy": "jwt", "secret": env("JWT_SECRET"),
                  "model": "database.models.user.User"},
        "admin": {"strategy": "jwt", "secret": env("ADMIN_JWT_SECRET"),
                  "model": "database.models.admin.Admin"},
    },
}
```

```python
from forgeapi.auth import guard

CurrentAdmin = guard("admin").current_user()   # dependency bound to the admin guard

@route.get("/admin/stats")
async def stats(self, admin: CurrentAdmin): ...

token = guard("admin").token(admin)            # per-guard token operations
```

Manual registration remains as an escape hatch:

```python
from forgeapi.auth import auth
from forgeapi.auth.guard import Guard
from forgeapi.auth.strategies import JWTStrategy

auth.register("api", Guard(name="api", strategy=JWTStrategy(secret_key="..."), user_model=User))
auth.set_default("api")
```

### Custom strategies — auth.extend()

```python
from forgeapi.auth import auth
from forgeapi.auth.strategies.base import AuthStrategy

class ApiKeyStrategy(AuthStrategy):
    @classmethod
    def from_config(cls, cfg: dict) -> "ApiKeyStrategy": ...

auth.extend("apikey", ApiKeyStrategy)
# now usable in config/auth.py: {"strategy": "apikey", ...}
```

Strategies raise **only** `ForgeAPIAuthError` subclasses — never
`HTTPException`, never touch the DB. That structural rule is what keeps all
strategies behaviourally identical at the edges.

### JWT strategy

Reads `Authorization: Bearer <token>`. Implements `TokenIssuer` + `RefreshCapable`.

| Config key | Default | Description |
|---|---|---|
| `secret` | — | Signing secret (use `env("JWT_SECRET")`) |
| `secret_env` | `"JWT_SECRET"` | Env var name to read when `secret` is not set |
| `algorithm` | `"HS256"` | JWT algorithm |
| `access_ttl` | `30` | Access token TTL, minutes |
| `refresh_ttl` | `7` | Refresh token TTL, days |

### Cookie strategy

Stores a signed JSON session in an `HttpOnly` cookie (HMAC). Implements `SessionIssuer`.

| Config key | Default | Description |
|---|---|---|
| `secret` | — | HMAC secret (use `env("COOKIE_SECRET")`) |
| `secret_env` | `"COOKIE_SECRET"` | Env var name to read when `secret` is not set |
| `cookie_name` | `"session"` | Cookie name |
| `max_age` | `3600` | Session lifetime, seconds |
| `httponly` | `True` | `HttpOnly` flag |
| `secure` | `True` | Set `False` only for local HTTP development |
| `samesite` | `"lax"` | SameSite policy |

```python
auth.set_cookie(response, {"sub": str(user.id)})
auth.delete_cookie(response)
```

### Telegram strategy

Validates `initData` from a Telegram Mini App. No login endpoint needed.

| Config key | Default | Description |
|---|---|---|
| `bot_token` | — | Bot token, or a list of tokens (use `env("BOT_TOKEN")`) |
| `bot_token_env` | `"BOT_TOKEN"` | Env var name to read when `bot_token` is not set |
| `max_age` | `86400` | Max `initData` age, seconds |

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

```python
# config/pagination.py
config = {
    "default_limit": 20,
    "max_limit": 100,
}
```

Always configured by `Core` — defaults apply when the file is absent.

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

Multiple listeners run **in parallel** via `asyncio.gather`. `Core(app)` imports all files in `listeners_dir` automatically when the directory exists.

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

**3. Nothing to register** — `Core(app)` scans `models_dir` and activates
permissions automatically when it finds the single `PermissionsMixin`
subclass (silently skips when there is none).

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

`Core` auto-configures `Cache` from `config/cache.py` on startup (memory driver by default).

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

```python
# config/cache.py
config = {
    "driver": "memory",                        # "memory" | "redis"
    "prefix": "",                              # key prefix, e.g. "myapp:"
    "ttl": None,                               # default TTL in seconds (None = no expiry)
    "redis_url": "redis://localhost:6379/0",   # used when driver = "redis"
}
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
```

Register via config (primary path) or `core.use()` (manual escape hatch):

```python
# config/http.py
from app.middleware import TimingMiddleware, TenantMiddleware
config = {
    "middleware": [
        TimingMiddleware,
        (TenantMiddleware, {"default_tenant": "acme"}),   # (cls, kwargs) tuple
    ],
}
```

```python
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

All configured in `config/http.py`:

```python
# config/http.py
config = {
    "cors": ["*"],        # True → all origins; list → specific; False → off
    "rate_limit": 60,     # req/min per IP; True → 60; False → off
    "request_id": True,   # inject X-Request-ID header
    "access_log": True,   # log method/path/status/duration per request
    "middleware": [],     # custom classes or (cls, kwargs) tuples
}
```

| Key | Default | Description |
|---|---|---|
| `cors` | `False` | `True` = allow all; list = specific origins |
| `rate_limit` | `False` | Sliding window per IP — returns `429` with `Retry-After` |
| `request_id` | `False` | Injects `X-Request-ID` header; access via `request.state.request_id` |
| `access_log` | `True` | Logs method, path, status, duration |

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

## 20. Configuration reference (config/)

The only config format is a **`config/` directory of Python dict files**
(Laravel-style). Each `config/<section>.py` defines a module-level
`config = {...}`; the filename is the section name. All sections are
optional — `Core(app)` works with no config files at all.
(`forgeapi.toml` is no longer supported — `load_config` raises with a
migration hint.)

### env() helper

```python
from forgeapi import env

env("APP_DEBUG", False)   # reads env var; casts "true"/"false"/"null"
env("JWT_SECRET")         # → str | None
```

### Known sections

```python
# config/project.py
from forgeapi import env
config = {
    "name": "my-app",
    "version": "0.1.0",
    "debug": env("APP_DEBUG", False),   # enables Telescope — never in production
    "providers": [],                    # extra Provider classes / dotted paths
}

# config/structure.py
config = {
    "models_dir": "database/models",
    "controllers_dir": "app/controllers",
    "schemas_dir": "app/schemas",
    "events_dir": "app/events",
    "listeners_dir": "app/listeners",
    "policies_dir": "app/policies",
    "seeds_dir": "database/seeds",
    "base_prefix": "/api/v1",
}

# config/http.py
config = {
    "cors": ["*"],
    "rate_limit": 60,
    "request_id": True,
    "access_log": True,
    "middleware": [],
}

# config/auth.py — see §5 for guard keys
config = {
    "default": "api",
    "guards": {
        "api": {"strategy": "jwt", "secret": env("JWT_SECRET"),
                "model": "database.models.user.User"},
    },
}

# config/pagination.py
config = {"default_limit": 20, "max_limit": 100}

# config/cache.py
config = {"driver": "memory", "prefix": "", "ttl": None,
          "redis_url": "redis://localhost:6379/0"}
```

### config/database.py

The `TORTOISE_ORM` dict lives here — that's all the file needs. The loader
derives the importable dotted path (`config.database.TORTOISE_ORM`) for the
tortoise CLI from the file location (`config/` is a namespace package):

```python
# config/database.py
import os
from dotenv import load_dotenv

load_dotenv()

TORTOISE_ORM = {
    "connections": {
        "default": os.getenv("DATABASE_URL", "sqlite://./db.sqlite3"),
    },
    "apps": {
        "models": {
            "models": ["database.models", "forgeapi.permissions.models"],
            "default_connection": "default",
            "migrations": "database.migrations",
        }
    },
}
```

An explicit `config = {"tortoise_orm": "app.settings.TORTOISE_ORM"}` is only
needed when the dict lives somewhere non-standard.

### Custom sections

Any extra file becomes a section, reachable with dot access:

```python
# config/services.py
config = {"stripe": {"key": env("STRIPE_KEY")}}
```

```python
core.config.get("services.stripe.key", default="")
core.config.get("auth.guards.api.strategy")
```

Known sections are validated by Pydantic models; misconfiguration raises
`ForgeAPIConfigError` with a hint. Feature enablement is decided by section
**presence** — e.g. auth boots only when the project provides `config/auth.py`.

---

## 21. Telescope

Debug-only request inspector activated by `"debug": True` in `config/project.py`. **Never use in production.**

```python
# config/project.py
from forgeapi import env
config = {"debug": env("APP_DEBUG", False)}
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
