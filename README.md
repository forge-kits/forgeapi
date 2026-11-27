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
   - [Cookie strategy](#cookie-strategy)
   - [Telegram strategy](#telegram-strategy)
6. [Pagination](#6-pagination)
   - [QuerySet .paginate()](#queryset-paginate)
   - [Offset pagination](#offset-pagination)
   - [Cursor pagination](#cursor-pagination)
7. [Broadcasting](#7-broadcasting)
   - [BroadcastManager](#broadcastmanager)
   - [Pub/Sub mode](#pubsub-mode)
   - [Stream mode](#stream-mode)
   - [Cross-project example](#cross-project-example)
   - [Registering handlers](#registering-handlers)
   - [Lifecycle](#lifecycle)
8. [Controllers](#8-controllers)
   - [Base pattern](#base-pattern)
   - [schema class var](#schema-class-var)
   - [Route decorator](#route-decorator)
   - [Auto-prefix and namespace](#auto-prefix-and-namespace)
9. [Schemas](#9-schemas)
   - [Pydantic in five minutes](#pydantic-in-five-minutes)
   - [Where they live](#where-they-live)
   - [The three schemas](#the-three-schemas)
   - [Base classes](#base-classes)
   - [Update schema: partial()](#update-schema-partial)
   - [Using schemas in a controller](#using-schemas-in-a-controller)
   - [Generating schemas: make:schema](#generating-schemas-makeschema)
   - [Hiding and removing fields](#hiding-and-removing-fields)
   - [Customising schemas](#customising-schemas)
10. [Policies](#10-policies)
11. [Database](#11-database)
    - [ModelMixin](#modelmixin)
    - [Soft Deletes](#soft-deletes)
    - [Query Scopes](#query-scopes)
    - [Observers](#observers)
    - [Factories](#factories)
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
14. [Storage](#14-storage)
    - [Configuration](#storage-configuration)
    - [Basic operations](#storage-basic-operations)
    - [Multiple disks](#multiple-disks)
    - [S3 / S3-compatible](#s3--s3-compatible)
    - [ImageProcessor](#imageprocessor)
15. [Support](#15-support)
    - [Number](#number)
    - [Str](#str)
    - [Time](#time)
16. [Logger](#16-logger)
17. [Middleware](#17-middleware)
    - [CORS](#cors)
    - [Rate limiting](#rate-limiting)
    - [Request ID](#request-id)
    - [Access logging](#access-logging)
18. [Settings](#18-settings)
19. [Seeders](#19-seeders)
20. [Scheduler](#20-scheduler)
21. [Queue](#21-queue)
    - [Defining a job](#defining-a-job)
    - [Dispatching](#dispatching)
    - [Running the worker](#running-the-worker)
    - [Failed jobs](#failed-jobs)
22. [Mail](#22-mail)
    - [Quick start](#quick-start)
    - [Configuration](#mail-configuration)
    - [Mailable](#mailable)
    - [Templates](#templates)
    - [Recipients and sender](#recipients-and-sender)
    - [Sending and queueing](#sending-and-queueing)
    - [Drivers](#drivers)
    - [Errors](#errors)
    - [Generating a mail](#generating-a-mail)
23. [CLI reference](#23-cli-reference)
24. [Configuration reference (config/)](#24-configuration-reference-config)
25. [MCP Server](#25-mcp-server)
26. [Testing](#26-testing)
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

SQLite + auth are included in the base package. Install extras only for production DB drivers or optional features.

| Extra | Installs | Use when |
|---|---|---|
| `asyncpg` | `asyncpg` | PostgreSQL |
| `aiomysql` | `aiomysql` | MySQL / MariaDB |
| `redis` | `redis` | Cache Redis driver / BroadcastManager events |
| `s3` | `boto3` | S3 / MinIO / Cloudflare R2 storage driver |
| `images` | `Pillow` | ImageProcessor helper |
| `mcp` | `mcp` | forge-kits MCP server for AI-assisted development |
| `dev` | `textual`, `faker` | tabbed interface of `forgeapi runserver`, `Factory` fake data |

```bash
pip install forge-kits               # SQLite included by default
pip install forge-kits[asyncpg]      # PostgreSQL
pip install forge-kits[aiomysql]     # MySQL / MariaDB
pip install forge-kits[redis]        # Redis cache / events
pip install forge-kits[mcp]          # MCP server
pip install forge-kits[dev]          # tabbed interface of `runserver`, Faker for factories
pip install forge-kits[s3,images]    # S3 storage + image processing
```

```bash
forgeapi init my-project
cd my-project

forgeapi db:migrate
forgeapi runserver --reload
```

`forgeapi init` asks for auth strategy (cookie / telegram) and DB driver (asyncpg / aiosqlite / aiomysql). It scaffolds the auth user model (`database/models/user.py`: `id`, `name`, `email`, `password`, `created_at`, `updated_at`) and, for the cookie strategy, `database/models/session.py` and `database/models/password_reset_token.py`. It generates the first migration (`database/migrations/0001_create_users_table.py`) for these tables, so only `forgeapi db:migrate` is left. Settings live in two files: `config/app.py` (project settings and a key per feature: `auth`, `http`, `pagination`, `storage`, `cache`, `mail`) and `config/database.py`. The opt-in features are commented out in `config/app.py`: `broadcast` (needs `pip install forge-kits[redis]`), `queue` and `scheduler`. Queue and scheduler also need their tables: `config/database.py` has the models (`forgeapi.queue.models`, `forgeapi.scheduling.models`, `forgeapi.cache.models`, `forgeapi.permissions.models`) as commented lines, uncomment the ones you use and run `forgeapi db:makemigrations`. If the migration cannot be generated (missing DB driver, no `tortoise` binary) `init` prints a warning and you run `forgeapi db:init && forgeapi db:makemigrations` yourself.

---

## 2. Project structure

After `forgeapi init my-project`:

```
my-project/
  main.py                    # entry point — FastAPI app + Core(app)
  .env                       # secrets (DB_* etc.)
  config/                    # settings (see §24)
    app.py                   # name, api_prefix, debug, providers, and a key per feature: auth, http, mail, ...
    database.py              # TORTOISE_ORM dict lives here
  app/
    controllers/             # *_controller.py files, auto-loaded by Core
    schemas/                 # Pydantic schemas
    events/                  # Event subclasses
  database/
    models/                  # Tortoise models
    migrations/              # migration files (tortoise CLI)
    seeds/                   # Seeder classes
```

The directory layout is fixed (not configurable). Paths are relative to the project root. `init` creates only the folders above; the others (`app/policies`, `app/jobs`, `app/mail`, `app/listeners`, `app/commands`, ...) appear when you run the matching `make:*` command:

| Directory | Holds |
|---|---|
| `database/models` | Tortoise models |
| `database/seeds` | seeders |
| `database/factories` | test factories (`make:factory`) |
| `app/controllers` | `*_controller.py`, discovered recursively |
| `app/schemas` | Pydantic schemas |
| `app/listeners` | broadcast event listeners |
| `app/policies` | policies |
| `app/jobs` | queue jobs |
| `app/observers` | model observers |
| `app/providers` | custom providers |
| `app/commands` | project CLI commands |

The only related setting is `api_prefix` in `config/app.py` (default `/api/v1`).

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
| Middleware stack | `"http"` in `config/app.py` (`cors`, `rate_limit`, `request_id`, `access_log`, `middleware`) |
| Auth guards | `"auth"` is in `config/app.py` |
| Storage | `"storage"` is in `config/app.py` — configures the `Storage` facade |
| Broadcasting | `"broadcast"` is in `config/app.py` — creates global `broadcast`, connects on startup, disconnects on shutdown |
| Scheduler | `"scheduler"` is in `config/app.py` — loads `schedule.py`, starts worker task on startup |
| Queue worker | `"queue"` is in `config/app.py` — starts worker task on startup |
| Controllers | `app/controllers` exists — all `*_controller.py` imported recursively |
| Event listeners | `"broadcast"` is in `config/app.py` — all files in `app/listeners` imported |
| Policies | `app/policies` exists — all `*_policy.py` imported |
| Permissions | a model in `database/models` inherits `PermissionsMixin` (no config needed) |
| Pagination, Cache | always configured (from their sections or defaults) |
| Custom providers | `"providers"` list in `config/app.py` |

`Core(app)` with no config files never raises — zero-config is a supported
starting point.

### Custom providers

```python
# config/app.py
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
# config/app.py
from forgeapi import env
config = {"debug": env("APP_DEBUG", False)}
```

Debug mode turns on verbose forgeapi logging (`DEBUG` level).
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

Auth is based on **Guards**. A Guard combines a **strategy** (how to verify credentials) with a required **user model** (which Tortoise model to load from the DB). A guard without `"model"` is a configuration error.

Available strategies: **cookie** (server-side sessions in the database, identified by a cookie), **telegram** (Telegram Mini App initData).

```
Auth (facade)   — guard registry + strategy factories, pure delegation
 └─ Guard       — the only layer that speaks HTTP (401) and loads users from the DB
     └─ AuthStrategy — extract/verify credentials, keep sessions (never touches user models)
```

### Step 1 — define guards in config/app.py

Auth boots automatically when `config/app.py` has an `"auth"` key — nothing to pass to `Core`.

```python
# config/app.py
from forgeapi import env

config = {
    "auth": {
        "default": "api",
        "guards": {
            "api": {
                "strategy": "cookie",           # cookie | telegram | custom
                "model": "database.models.user.User",   # required — user is always loaded from the DB
            },
        },
    },
}
```

`strategy` picks the credential mechanism; the remaining keys are passed to
the strategy's `from_config()` (see per-strategy tables below). `model` is a
required dotted path to a Tortoise model: `CurrentUser` always resolves to a real
DB instance (and a valid session whose user is gone from the DB is a 401).
A guard without `model` raises `ForgeAPIConfigError` at startup.

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
- credentials **present but invalid** (expired / unknown session / user gone
  from the DB) → **401 always**, even for `OptionalUser`
- every 401 carries `WWW-Authenticate: Bearer error="<code>"` with a
  machine-readable code: `session_expired`, `session_invalid`, `user_not_found`, `missing_credentials`

### What the user object contains

The dependency returns your **Tortoise model instance** loaded from the DB
(looked up by primary key from the session), so all its fields and
methods are available. `CurrentUser` and `OptionalUser` are typed `Any`; use
`guard("api").current_user()` for a dependency typed as the guard's model.

### Auth facade — session operations

```python
from forgeapi.auth import auth

# Cookie strategy, the cookie is set through AuthMiddleware, no response needed
await auth.login(user)                 # start a session
await auth.logout()                    # end it and remove the cookie
await auth.logout_others(user)         # every other device, e.g. after a password change
```

### Login / Logout endpoint pattern (cookie)

```python
@route.post("/login")
async def login(self, payload: LoginPayload) -> dict:
    user = await User.get_or_none(email=payload.email)
    if not user or not user.verify_password(payload.password):
        raise HTTPException(401, "Invalid credentials")
    await auth.login(user)
    return {"message": "Logged in"}

@route.post("/logout")
async def logout(self) -> dict:
    await auth.logout()
    return {"message": "Logged out"}
```

### Multiple guards

```python
# config/app.py
config = {
    "auth": {
        "default": "api",
        "guards": {
            "api":   {"strategy": "cookie",
                      "model": "database.models.user.User"},
            "admin": {"strategy": "cookie", "cookie_name": "admin_session",
                      "model": "database.models.admin.Admin"},
        },
    },
}
```

Each guard has its own sessions, so a cookie of one guard never logs in to another. Give guards that share a browser different `cookie_name` values.

```python
from forgeapi.auth import guard

CurrentAdmin = guard("admin").current_user()   # dependency bound to the admin guard

@route.get("/admin/stats")
async def stats(self, admin: CurrentAdmin): ...
```

Manual registration remains as an escape hatch:

```python
from forgeapi.auth import auth
from forgeapi.auth.guard import Guard
from forgeapi.auth.strategies import CookieStrategy

auth.register("api", Guard(name="api", strategy=CookieStrategy(), user_model=User))
auth.set_default("api")
```

### Custom strategies — auth.extend()

```python
from forgeapi.auth import auth
from forgeapi.auth.strategies.base import AuthStrategy

class ApiKeyStrategy(AuthStrategy):
    @classmethod
    def from_config(cls, cfg: dict) -> "ApiKeyStrategy": ...

    async def authenticate(self, request):
        key = request.headers.get("X-Api-Key")
        if not key:
            return None                 # no credentials
        return lookup_user_id(key)      # user id (primary key)

auth.extend("apikey", ApiKeyStrategy)
# now usable in the "auth" section of config/app.py: {"strategy": "apikey", ...}
```

`authenticate()` returns only the user id (`str` or `int`), or `None` when credentials are absent.
The guard loads the user from the DB by that id, using the guard's `user_model`.

Strategies raise **only** `ForgeAPIAuthError` subclasses — never
`HTTPException`, never touch user models.

### Cookie strategy

Keeps login sessions in the `sessions` table of your project. The cookie holds only a random token, the table holds its SHA-256 hash. A logout deletes the session, so a copied cookie stops working at once.

`forgeapi init` creates the model in `database/models/session.py` (and `password_reset_token.py` next to it), so you can change the table. The guard points to it with `"session_model"`. The model needs the fields `id` (64 characters, primary key), `user_id`, `guard`, `ip_address`, `user_agent`, `created_at`, `last_activity` and `expires_at`, add your own freely. `Core` adds `AuthMiddleware` when `config/app.py` has an `"auth"` key, it sets the cookie for `auth.login()` and `auth.logout()`.

Expired sessions are deleted when they are read, and one login in 50 deletes all the expired ones.

| Config key | Default | Description |
|---|---|---|
| `session_model` | required | Dotted path of the model that holds the sessions, `"database.models.session.Session"` after `init` |
| `cookie_name` | `"session"` | Cookie name |
| `lifetime` | `3600` | Seconds of inactivity after which the session expires, every request moves it forward |
| `absolute_lifetime` | `None` | Seconds after which the session ends however active it is |
| `httponly` | `True` | `HttpOnly` flag |
| `secure` | `True` | Set `False` only for local HTTP development |
| `samesite` | `"lax"` | SameSite policy |

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

Three methods on every QuerySet — no dependency injection, no `request` argument.

### paginate()

Two queries (COUNT + SELECT). Full meta with `total` and `last_page`:

```python
from forgeapi.controllers import Controller, route

class PostController(Controller):
    prefix = "/posts"
    tags   = ["posts"]

    @route.get("/", response_model=None)
    async def index(self):
        return await Post.all().order_by("-created_at").paginate(15, PostResponse)

    @route.get("/published", response_model=None)
    async def published(self):
        return await Post.filter(is_published=True).paginate(15, PostResponse)
```

Query params: `?page=1&per_page=20`. Response:

```json
{
  "data": [...],
  "meta": {
    "current_page": 1,
    "per_page": 15,
    "total": 47,
    "last_page": 4,
    "from": 1,
    "to": 15
  },
  "links": {
    "prev": null,
    "next": "/posts?page=2&per_page=15"
  }
}
```

`schema` is optional — omit to get raw ORM objects. Explicit `per_page` argument overrides `?per_page` query param.

### simple_paginate()

One query (SELECT N+1, no COUNT). Only `prev`/`next` links — faster on large tables:

```python
@route.get("/", response_model=None)
async def index(self):
    return await Post.all().order_by("-created_at").simple_paginate(15, PostResponse)
```

Response has no `total` or `last_page` in `meta`.

### cursor_paginate()

No OFFSET — stable and O(1) on large datasets, stable on concurrent inserts/deletes:

```python
@route.get("/", response_model=None)
async def index(self):
    return await Post.all().cursor_paginate(15, PostResponse, order_by="-id")
```

Query params: `?cursor=<token>&per_page=20`.

### Configuration

```python
# config/app.py
config = {
    "pagination": {
        "default_limit": 20,
        "max_limit": 100,
    },
}
```

Always configured by `Core` — defaults apply when the file is absent.

---

## 7. Broadcasting

`BroadcastManager` is the universal event bus for both in-process and cross-project messaging. Pluggable driver system — Redis now, RabbitMQ/Kafka via `register_driver()`.

### Config-driven setup (with Core)

Add a `"broadcast"` key to `config/app.py` — `Core(app)` does the rest: creates the global `broadcast` proxy, imports all listeners, and manages connect/disconnect via FastAPI startup/shutdown hooks.

All driver-specific options go under `driver_options` — the manager itself is driver-agnostic.

```python
# config/app.py — pubsub mode
from forgeapi import env

config = {
    "broadcast": {
        "driver": "redis",
        "driver_options": {
            "url": env("REDIS_URL", "redis://localhost:6379"),
            "namespace": "shop",
            "mode": "pubsub",
        },
    },
}
```

```python
# config/app.py — stream mode (persistent, survives restarts)
from forgeapi import env

config = {
    "broadcast": {
        "driver": "redis",
        "driver_options": {
            "url": env("REDIS_URL", "redis://localhost:6379"),
            "namespace": "shop",
            "mode": "stream",
            "group": "backend",
            "consumer": "worker-1",
            "maxlen": 1000,        # keep last N messages per stream key
        },
    },
}
```

Generate a listener with `forgeapi make:listener OrderCreated` (the event name becomes `order:created`), or write it by hand:

```python
# app/listeners/order_listener.py
from forgeapi.broadcasting import broadcast

@broadcast.on("order:created")
async def handle(data: dict) -> None:
    print(data["id"])
```

```python
# main.py — no lifespan needed, BroadcastProvider handles connect/disconnect
from fastapi import FastAPI
from forgeapi import Core

app = FastAPI()
core = Core(app)
```

### Modes

| | `mode="pubsub"` | `mode="stream"` |
|---|---|---|
| Persistence | None — messages lost if subscriber is offline | Stored until all groups ACK |
| Delivery | All subscribers simultaneously | Each group independently |
| Offline workers | Miss messages | Catch up on reconnect |
| Horizontal scaling | — | Multiple consumers per group share load |

### Standalone / Cross-project usage

Use `BroadcastManager` directly outside a Core-managed app (standalone bot, worker process, publisher-only script).

All driver-specific options are keyword arguments — they are forwarded as-is to the driver constructor:

```python
from forgeapi.broadcasting import BroadcastManager

# Publisher only (no listeners registered — starts in emit-only mode)
broadcast = BroadcastManager(
    driver="redis",
    url="redis://localhost:6379",
    namespace="shop",
    mode="stream",
)

await broadcast.connect()
await broadcast.emit("order:created", {"id": 42, "total": 99.0})
await broadcast.disconnect()
```

```python
# Consumer (standalone asyncio script)
broadcast = BroadcastManager(
    driver="redis",
    url="redis://localhost:6379",
    namespace="shop",
    mode="stream",
    group="telegram-bot",
    consumer="worker-1",
)

@broadcast.on("order:created")
async def handle(data: dict) -> None:
    print(f"New order #{data['id']}")

async def main() -> None:
    await broadcast.run()   # connect + listen in foreground, Ctrl+C stops cleanly

asyncio.run(main())
```

`emit()` accepts a plain `dict` — serialization (datetime, UUID, Decimal) is handled internally by the driver.

---

## 8. Controllers

Controllers group routes. `Core` auto-discovers all `*_controller.py` files in `app/controllers` (recursively) and registers their routers under `api_prefix`.

### Base pattern

```python
from fastapi import Request
from forgeapi.controllers import Controller, route
from forgeapi.auth import CurrentUser
from database.models.post import Post
from app.schemas.post import PostResponse, PostCreate, PostUpdate


class PostController(Controller):
    prefix = "/posts"
    tags   = ["posts"]
    schema = PostResponse   # auto response_model (see below)

    @route.get("/", response_model=None)
    async def index(self):
        return await Post.all().order_by("-created_at").paginate(15, PostResponse)

    @route.post("/", status_code=201)
    async def create(self, payload: PostCreate, user: CurrentUser):
        return await Post.create_from(payload, author_id=int(user.id))

    @route.get("/{id}")
    async def show(self, id: int):
        return await Post.find_or_fail(id)

    @route.patch("/{id}")
    async def update(self, id: int, payload: PostUpdate, user: CurrentUser):
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
    async def index(self):
        return await Post.all().paginate(15, PostResponse)

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

Final URL = `api_prefix` + `controller.prefix` + `route path`

```bash
forgeapi make:controller Post          # controllers/post_controller.py
forgeapi make:controller AdminUser     # controllers/admin/user_controller.py
```

---

## 9. Schemas

Schemas are Pydantic models that describe what goes into the API and what comes out of it.
forge-kits keeps **one file per resource** with **three classes**.

### Pydantic in five minutes

forge-kits schemas are plain [Pydantic](https://docs.pydantic.dev) models (Pydantic v2). FastAPI uses them to check what a client sends and to shape what it gets back. If you know this page, you know everything the schemas rely on.

**A model is a class with typed fields.** Creating an object checks the data and converts what it can:

```python
from pydantic import BaseModel, ValidationError


class User(BaseModel):
    name: str                  # required: no default
    age: int
    email: str | None = None   # optional: may be missing or None
    active: bool = True        # optional: has a default


User(name="Ana", age="30")     # name='Ana' age=30 ...   "30" was converted to the number 30
User(name="Ana", age="abc")    # ValidationError: age, "Input should be a valid integer"
User(age=3)                    # ValidationError: name is missing
```

FastAPI turns a `ValidationError` on the request body into a `422` response that lists every wrong field, so you never write that check yourself.

**Constraints and validators** describe what a valid value is:

```python
from pydantic import BaseModel, Field, field_validator


class PostCreate(BaseModel):
    title: str = Field(min_length=3, max_length=100)    # length limits
    views: int = Field(0, ge=0)                         # default 0, never negative

    @field_validator("title")
    @classmethod
    def strip(cls, value: str) -> str:                  # runs after the type check
        return value.strip()                            # may change the value or raise ValueError
```

**Reading data.** `Model.model_validate(data)` builds a model from a dict. With `from_attributes=True` (which `BaseSchema` sets) it also reads an object's attributes, which is how a Tortoise instance becomes a response: `PostResponse.model_validate(post)`.

**Writing data.** `model.model_dump()` gives a dict. Three switches decide which fields are in it:

| Call | Leaves out |
|---|---|
| `model_dump()` | nothing |
| `model_dump(exclude_none=True)` | fields whose value is `None` |
| `model_dump(exclude_unset=True)` | fields the caller never passed (even if the default is not `None`) |
| `model_dump(exclude={"age"})` | the named fields |

`Schema.changes()` in forge-kits is `model_dump(exclude_unset=True)`.

**In an API** each direction gets its own model: one for what comes in (`PostCreate`), one for what goes out (`PostResponse`). A field that exists only on the input model (a password) can never leak, because the output model does not declare it. That is why forge-kits uses three classes per resource.

### Where they live

```
app/
  schemas/
    post.py        # PostCreate, PostUpdate, PostResponse
    user.py        # UserCreate, UserUpdate, UserResponse
```

- The folder is fixed: `app/schemas/`. Input and output of one resource sit side by side in one file.
- The file name is the model name in snake_case (`Post` → `post.py`, `AdminUser` → `admin_user.py`).
- `forgeapi init` does not create the folder. `forgeapi make:schema` (or `make:model -s`, `make:controller -s`) creates it with the first schema.

### The three schemas

| Class | Used for | Built from |
|---|---|---|
| `PostCreate` | body of `POST` | `Schema` |
| `PostUpdate` | body of `PATCH` | `PostCreate.partial()`: the same fields, all optional |
| `PostResponse` | what the API returns | `BaseSchema` (reads Tortoise instances) |

```python
from forgeapi import BaseSchema, Schema


class PostCreate(Schema):
    title: str
    body: str | None = None


PostUpdate = PostCreate.partial("PostUpdate")   # title and body become optional


class PostResponse(BaseSchema):
    title: str
    body: str | None = None
```

### Base classes

**`BaseSchema`** – the response base.

- Fields: `id` (required, `int` or `str`), `created_at` and `updated_at` (`datetime | None = None`).
- `created_at` / `updated_at` are filled when the model has them. A model without timestamp columns still validates, those two fields are `None`.
- `from_attributes=True`, so a Tortoise instance goes straight in: `PostResponse.model_validate(post)`.
- Subclasses add their own fields. `id` and the timestamps are never repeated in them.

**`Schema`** – the base for input schemas (request bodies). It is a Pydantic `BaseModel` with two helpers, everything else is plain Pydantic (types, `Field(...)`, validators):

- `Schema.partial(name)` returns a copy where every field is optional. It is how the update schema is made, see below.
- `payload.changes()` returns only the fields the client actually sent, as a dict (`model_dump(exclude_unset=True)`). A field sent as `null` is kept, so a PATCH can clear a value.

You may use `pydantic.BaseModel` directly instead of `Schema`: nothing else in forge-kits requires it, you only lose the two helpers.

### Update schema: `partial()`

**The problem.** `POST` creates a post, so the client must send `title` and `body`. `PATCH` changes a post, and the client sends only what it wants to change, for example just `title`. So the update schema needs the same fields as the create schema, **all optional**. Writing it by hand means repeating every field and its limits, and forgetting to update it when a field is added:

```python
class PostCreate(Schema):
    title: str = Field(min_length=3)
    body: str


class PostUpdate(Schema):                    # the same fields typed again
    title: str | None = Field(None, min_length=3)
    body: str | None = None
```

**The solution.** `PostCreate.partial("PostUpdate")` returns a copy of the schema where **every field is optional** (default `None`). The update payload is derived from the create one, so there is nothing to keep in sync when a field is added.

```python
from pydantic import Field
from forgeapi import Schema


class PostCreate(Schema):
    title: str = Field(min_length=3, max_length=100)
    views: int = Field(0, ge=0)


PostUpdate = PostCreate.partial("PostUpdate")

PostUpdate()                  # valid: nothing to change
PostUpdate(title="New title") # valid
PostUpdate(title="ab")        # ValidationError: too short
PostUpdate(views=-1)          # ValidationError: must be >= 0
```

What it does and does not do:

- Constraints (`Field(min_length=...)`, `ge`, `pattern`) and validators stay and run **only for the fields the client sends**.
- The original schema is not changed: `PostCreate()` still requires `title`.
- `name` is the class name shown in OpenAPI. Without it the name is `<Class>Partial`, so always pass it.
- The result is a `Schema` too, so `changes()` works on it.
- It builds a class at runtime, so editors do not autocomplete the fields of `PostUpdate`. They still appear in the OpenAPI schema and validate correctly.
- If PATCH must accept different fields than POST, write the class by hand:

```python
class PostUpdate(Schema):
    title: str | None = None
    is_published: bool | None = None     # exists only for updates
```

### Using schemas in a controller

```python
from forgeapi.auth import CurrentUser
from forgeapi.controllers import Controller, route
from database.models.post import Post
from app.schemas.post import PostCreate, PostUpdate, PostResponse


class PostController(Controller):
    prefix = "/posts"
    schema = PostResponse                       # response_model for every route (see "schema class var")

    @route.get("/", response_model=None)
    async def index(self):
        return await Post.all().order_by("-created_at").paginate(15, PostResponse)

    @route.post("/", status_code=201)
    async def create(self, payload: PostCreate, user: CurrentUser):
        return await Post.create_from(payload, author_id=int(user.id))

    @route.patch("/{id}")
    async def update(self, id: int, payload: PostUpdate):
        post = await Post.find_or_fail(id)
        return await post.update_from(payload)
```

- **Validation.** FastAPI validates the body against `PostCreate` / `PostUpdate` and answers `422` with the details when it does not match.
- **Server-set fields.** `author_id` above comes from the logged-in user, not from the client. Remove such fields from `PostCreate`, otherwise the client has to send them (make:schema copies every model field, see below).
- **`create_from` / `update_from`** save `payload.model_dump(exclude_none=True)`. Two consequences: a field the client left out never overwrites the database value (this is what makes PATCH partial), and a client **cannot set a field to `null`** through these methods. To let a PATCH clear a value, apply what the client sent with `changes()`, which keeps fields sent as `null`:

  ```python
  post.update_from_dict(payload.changes())
  await post.save()
  ```
- **Responses.** `schema = PostResponse` on the controller sets `response_model` for all routes, which also filters out any model attribute the schema does not declare. `.paginate(15, PostResponse)` returns the paginated envelope with items serialised by the schema, so `response_model=None` is used on that route.

### Generating schemas: `make:schema`

```bash
forgeapi make:schema Post                       # app/schemas/post.py
forgeapi make:schema User --exclude internal    # leave a model field out of all three classes
forgeapi make:model Post -s                     # model + schema
forgeapi make:controller Post --ms              # model + schema + controller
```

If `database/models/post.py` exists, the fields are read from the model. Without a model the classes are empty stubs with a `TODO`, and the command says so.

For a model with `title`, a nullable `body`, `views` (default `0`), `is_published` (default `False`) and a foreign key `author`, it writes:

```python
from __future__ import annotations

from forgeapi import BaseSchema, Schema


class PostCreate(Schema):
    title: str
    author_id: int
    body: str | None = None
    views: int = 0
    is_published: bool = False


PostUpdate = PostCreate.partial("PostUpdate")


class PostResponse(BaseSchema):
    title: str
    body: str | None = None
    views: int
    is_published: bool
    author_id: int
```

**How the fields are mapped**

| Model field | Schema type |
|---|---|
| `CharField`, `TextField`, `EmailField`, `URLField`, `IPAddressField` | `str` |
| `IntField`, `BigIntField`, `SmallIntField` | `int` |
| `FloatField` | `float` |
| `DecimalField` | `Decimal` |
| `BooleanField` | `bool` |
| `DatetimeField`, `DateField`, `TimeField` | `datetime`, `date`, `time` |
| `UUIDField` | `UUID` |
| `JSONField` | `Any` |
| `BinaryField` | `bytes` |
| enum fields (`CharEnumField`, `IntEnumField`) | the enum class, with its import |
| other custom fields | their `python_type`, or `Any` when there is none |
| `ForeignKeyField`, `OneToOneField` (`author`) | `author_id: int` |
| reverse relations, many-to-many | skipped |

**Rules the generator follows**

- `id`, `created_at` and `updated_at` are not repeated: they come from `BaseSchema`.
- `PostCreate`: required fields first, then optional ones. A nullable field becomes `X | None = None`. A field with a literal default (number, string, boolean, enum member) keeps it.
- `PostResponse`: a nullable field is `X | None = None`, every other field is required and has no default.
- **Credential-looking fields stay in `Create` and are left out of `Response`.** The match is on the field name: `password`, `passwd`, `secret`, `token`, `api_key`, or a name ending in `_hash`. The command prints which fields it left out, for example `PostResponse leaves out: password_hash`.
- `--exclude a,b` removes the named model fields from **all three** classes. An unknown name only produces a warning.
- **An existing file is never overwritten.** Re-running the command prints `exists` and changes nothing, so edit schemas freely.

**Check the result before committing it.** The generator copies every model field into `PostResponse` except the credential-looking ones. A field with another name that must not leave the server (an internal note, a 2FA seed, a card number) has to be removed by hand or with `--exclude`.

**Known limits** (they come from the generator, not from Pydantic)

- A foreign key is always `int`. For a model whose primary key is a `UUID` or a string, change the type by hand.
- A callable default (`default=uuid4`, `default=list`, `default=datetime.now`) is not copied. Such a field is required in `Create` unless it is nullable: give it a default by hand.
- A primary key not named `id` is treated as an ordinary field.

### Hiding and removing fields

There are four tools. Pick by what you want to achieve:

| Goal | Use |
|---|---|
| Leave a model field out of the **generated** schemas | `forgeapi make:schema User --exclude internal_note` |
| Accept a field on input but **never send it back** | declare it in `Create`, not in `Response` (done for you for credential-looking names) |
| One class used in both directions, but a field must not be returned | `Field(exclude=True)` on that field |
| Drop fields for one particular call | `model.model_dump(exclude={"name"})` |

**`--exclude` (generator).** Names model fields to skip in **all three** classes: `PostCreate`, `PostUpdate` and `PostResponse`.

```bash
forgeapi make:schema User --exclude internal_note,legacy_id
```

An unknown name only prints a warning. It affects the generated file only: edit the file afterwards as you like, a rerun never overwrites it.

**Fields that look like credentials** (`password`, `passwd`, `secret`, `token`, `api_key`, names ending in `_hash`) are excluded from `Response` **automatically**, and stay in `Create`. Other sensitive names (an internal note, a card number) are not recognised: remove them from `Response` by hand or pass them to `--exclude`.

**Separate input and output classes** are the main protection. `UserResponse` returns only the fields it declares, whatever the model has:

```python
class UserCreate(Schema):
    email: str
    password: str                    # accepted from the client


class UserResponse(BaseSchema):
    email: str                       # password is not declared, so it is never returned
```

**`Field(exclude=True)`** keeps a field when reading input and removes it from every output (`model_dump()`, JSON, FastAPI responses). Useful when one class serves both directions:

```python
from pydantic import BaseModel, Field


class Account(BaseModel):
    email: str
    password: str = Field(exclude=True)


Account(email="a@b.com", password="secret").model_dump()   # {'email': 'a@b.com'}
# used as request body and as response_model, FastAPI accepts "password" and does not return it
```

**`model_dump(exclude=...)`** removes fields for a single call, for example before logging or saving:

```python
payload.model_dump(exclude={"password"})
```

`create_from` and `update_from` already skip `None` values (`exclude_none=True`). For a PATCH that must tell "not sent" from "sent as null", use `payload.changes()`.

### Customising schemas

The generated file is yours. Common edits:

```python
from pydantic import EmailStr, Field, computed_field, field_validator


class UserCreate(Schema):
    email: EmailStr                                   # stricter type than the generated `str`
    password: str = Field(min_length=8)

    @field_validator("email")
    @classmethod
    def lowercase(cls, v: str) -> str:
        return v.lower()


UserUpdate = UserCreate.partial("UserUpdate")  # inherits the validators and constraints


class UserResponse(BaseSchema):
    email: str
    posts_count: int = 0                              # fill it before returning

    @computed_field
    @property
    def display_name(self) -> str:
        return self.email.split("@")[0]
```

Nested output, for a model with a loaded relation:

```python
class AuthorResponse(BaseSchema):
    username: str


class PostResponse(BaseSchema):
    title: str
    author: AuthorResponse | None = None             # needs .prefetch_related("author")
```

The MCP tool `generate_schema(name, fields, mode)` produces the same three classes as source text, for assistants that generate code without a model file.

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
async def update(self, id: int, payload: PostUpdate, user: CurrentUser):
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

## 11. Database

### ModelMixin

`ModelMixin` adds ORM shortcuts and enables `.paginate()` on every QuerySet. Mix it alongside `tortoise.Model`:

```python
from tortoise import Model, fields
from forgeapi import ModelMixin
from forgeapi.database import scope

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

    @scope
    def published(qs):
        return qs.filter(is_published=True)

    @scope
    def by_author(qs, author_id: int):
        return qs.filter(author_id=author_id)
```

Use `@scope` (not `@classmethod`) for reusable filters — see [Query Scopes](#query-scopes).
`Post.observe(PostObserver)` registers lifecycle hooks — see [Observers](#observers).

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

### QuerySet pagination

`ModelMixin` injects `ForgeManager` automatically so pagination methods are available on every QuerySet chain:

```python
# Full paginated response (COUNT + SELECT)
result = await Post.all().order_by("-created_at").paginate(15, PostResponse)

# No COUNT — faster on large tables
result = await Post.all().order_by("-created_at").simple_paginate(15, PostResponse)

# Cursor-based — no OFFSET
result = await Post.all().cursor_paginate(15, PostResponse, order_by="-created_at")

# With filters
result = await Post.published().paginate(15, PostResponse)
result = await Post.by_author(user_id).order_by("-created_at").paginate(15, PostResponse)

# Without schema — returns raw ORM objects
result = await Post.all().paginate(15)
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

### Soft Deletes

Use `SoftDeleteMixin` instead of `ModelMixin` to get soft delete support. Sets `deleted_at` instead of issuing a DELETE.

```python
from forgeapi.database import SoftDeleteMixin

class Post(SoftDeleteMixin, Model):
    title = fields.CharField(max_length=255)
```

```python
await post.delete()        # sets deleted_at — row stays in DB
await post.restore()       # clears deleted_at
await post.force_delete()  # permanent DELETE
post.is_trashed            # True if deleted_at is set
```

All default queries automatically exclude soft-deleted records:

```python
Post.all()                        # excludes soft-deleted
Post.all().with_trashed()         # includes soft-deleted
Post.all().only_trashed()         # only soft-deleted
Post.filter(author_id=1).with_trashed().paginate(15, PostResponse)
```

`find_or_fail()` also excludes soft-deleted records — raises 404 if the record is trashed.

---

### Query Scopes
query scopes — reusable, chainable filters defined on the model.

```python
from tortoise import Model, fields
from forgeapi.database import ModelMixin, scope

class Post(ModelMixin, Model):
    title = fields.CharField(max_length=255)
    is_published = fields.BooleanField(default=False)
    author_id = fields.IntField()

    @scope
    def published(qs):
        return qs.filter(is_published=True)

    @scope
    def by_author(qs, author_id: int):
        return qs.filter(author_id=author_id)
```

### Using scopes

Call scopes directly on the queryset — they chain like regular filters:

```python
# class-level (creates a fresh queryset)
posts = await Post.published()
posts = await Post.by_author(42)

# chaining
posts = await Post.published().order_by("-created_at").limit(20)
posts = await Post.all().published().by_author(42)
```

The `@scope` decorator registers the method in `_scopes` on the model class and
makes it available on any queryset of that model via `__getattr__`.  No base
queryset class change required.

---

### Observers

Lifecycle hooks fired by Tortoise signals — audit logs, cache invalidation,
notifications — without scattering the logic across controllers.

```python
from forgeapi.database import ModelObserver

class PostObserver(ModelObserver):
    async def creating(self, instance, **kw): ...   # before first save
    async def created(self, instance, **kw): ...    # after first save
    async def updating(self, instance, **kw): ...   # before update save
    async def updated(self, instance, **kw): ...    # after update save
    async def saving(self, instance, **kw): ...     # before any save
    async def saved(self, instance, **kw): ...      # after any save
    async def deleting(self, instance, **kw): ...   # before delete
    async def deleted(self, instance, **kw): ...    # after delete
```

Override only the hooks you need — `ModelObserver` provides empty defaults for
all of them.

### Registering

```python
# class-based (instantiated automatically)
Post.observe(PostObserver)

# instance-based (useful for inline/test observers)
class _Audit(ModelObserver):
    async def created(self, instance, **kw):
        await AuditLog.create(action="post.created", target_id=instance.id)

Post.observe(_Audit())
```

### Example — cache invalidation

```python
class PostObserver(ModelObserver):
    async def saved(self, instance, **kw):
        await Cache.forget(f"post:{instance.id}")
        await Cache.forget("posts:index")

    async def deleted(self, instance, **kw):
        await Cache.forget(f"post:{instance.id}")

Post.observe(PostObserver)
```

Register observers at startup (e.g. in `main.py` or a custom Provider's
`boot()`) — before any requests arrive.

### Factories

A factory creates a model with fake data. `definition()` lists the values of a new record, and `fake` (Faker) gives the data:

```python
from forgeapi.database import Factory, fake

class UserFactory(Factory[User]):
    model = User

    def definition(self):
        return {
            "name": fake.name(),
            "email": fake.unique.email(),
            "password": "password",
        }

    def admin(self):                 # a named state
        return self.state(role="admin")

user   = await UserFactory.create()
admin  = await UserFactory.admin().create(name="Ann")
users  = await UserFactory.count(5).create()
data   = await UserFactory.make()            # a dict, nothing is saved
```

A relation is another factory used as a value, it is created together with the record:

```python
class PostFactory(Factory[Post]):
    model = Post

    def definition(self):
        return {"author": UserFactory(), "title": fake.sentence()}

post = await PostFactory.create()                       # creates its author too
post = await PostFactory.create(author=some_user)       # uses an existing one
```

Values passed to `create()` and `state()` win over `definition()`. A required field that `definition()` does not list is not filled in: the model raises its usual validation error.

Tests use them as plain pytest: see [Testing](#26-testing).

---

## 12. Permissions

Roles and permissions using polymorphic pivot tables.

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

**3. Nothing to register** — `Core(app)` scans `database/models` and activates
permissions automatically when it finds the single `PermissionsMixin`
subclass (silently skips when there is none).

**4. Run migrations:**

```bash
forgeapi db:makemigrations && forgeapi db:migrate
```

### PermissionsMixin

Guard namespace resolves automatically — no need to pass it when the model is registered in auth config:

```python
# Guard resolves automatically via auth config (User → "api", Worker → "worker")
await user.can("edit:posts")                     # checks "api" namespace
await worker.can("view:tasks")                   # checks "worker" namespace
await user.can("edit:posts", "admin")            # OR logic
await user.cannot("delete:users")
await user.has_all_permissions("read", "write")  # AND logic
await user.has_role("admin")
await user.has_all_roles("admin", "editor")

# Granting / revoking — guard resolved from model automatically
await user.give_permission("edit:posts", "delete:posts")
await user.revoke_permission("delete:posts")
await user.assign_role("admin", "editor")
await user.remove_role("editor")

# Explicit override when needed:
await user.give_permission("cross:action", guard="worker")

# Listing
await user.get_all_permissions()   # → ["edit:posts", ...]
await user.get_role_names()        # → ["admin", "editor"]
```

### Dependencies

```python
from forgeapi.permissions import require_permission, require_role

# Guard resolved automatically from the authenticated model's auth config registration:
@route.delete("/{id}")
async def destroy(self, id: int, user=require_permission("delete:posts")): ...

@route.post("/")
async def create(self, payload, user=require_permission("create:posts", "admin")): ...  # OR

@route.get("/admin/stats")
async def stats(self, user=require_role("admin")): ...

# Non-default guard — authenticates with "worker" guard, resolves Worker model:
@route.post("/tasks")
async def create_task(self, user=require_permission("create:tasks", guard="worker")): ...

@route.get("/dashboard")
async def dashboard(self, user=require_role("supervisor", guard="worker")): ...
```

Both dependencies also check `db_user.is_active` when the field exists — inactive users receive `401`.

`guard` in `require_permission`/`require_role` selects which auth guard authenticates the request. The permission/role namespace is then resolved automatically from the returned model's auth config registration.

### Role and Permission models

`name` is unique **per guard** — you can have `"admin"` for `"api"` and a separate `"admin"` for `"worker"`. The `guard` field is always set — never NULL in practice (Python raises `ValueError` if it resolves to empty).

```python
from forgeapi.permissions.models import Role, Permission

role = await Role.find_or_create("editor")                   # uses auth._default
role = await Role.find_or_create("supervisor", guard="worker")

await role.give_permission("edit:posts", "read:posts")       # inherits role.guard
await role.has_permission("edit:posts")                      # → bool, uses role.guard

# Filtering by role
users = await (await User.with_role("admin"))                # guard resolved from User
users = await (await User.without_role("admin"))
```

---

## 13. Cache

Async key-value cache. Two drivers: **database** (default, stored in the app's DB) and **redis** (faster, shared across workers).

`Core` auto-configures `Cache` from the `"cache"` section of `config/app.py` on startup (database driver by default).

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
async def popular(self):
    cached = await Cache.get("posts:popular")
    if cached:
        return cached
    result = await Post.filter(is_published=True).paginate(15, PostResponse)
    await Cache.set("posts:popular", result, ttl=60)
    return result
```

### Drivers

| Driver | When to use |
|---|---|
| `database` | Default. Table `cache` in the project DB, shared across workers, survives restarts. Needs `forgeapi.cache.models` in `TORTOISE_ORM` |
| `redis` | Multiple workers, production. Requires `pip install forge-kits[redis]` |

### Cache configuration

```python
# config/app.py
config = {
    "cache": {
        "driver": "database",                      # "database" | "redis"
        "prefix": "",                              # key prefix, e.g. "myapp:"
        "ttl": None,                               # default TTL in seconds (None = no expiry)
        "redis_url": "redis://localhost:6379/0",   # used when driver = "redis"
    },
}
```

The database driver needs the table. Add the model to `config/database.py` and run the migration:

```python
"models": ["database.models", "forgeapi.cache.models"],
```

Expired rows are deleted when they are read. To purge the ones that are never read again, call
`DatabaseDriver().prune()` from a scheduled task.

Programmatic setup (without Core):

```python
from forgeapi import Cache

Cache.configure(driver="redis", prefix="myapp:", ttl=3600, redis_url="redis://localhost:6379/1")
```

---

## 14. Storage

File storage abstraction with Local and S3-compatible drivers. Configured via
the `"storage"` key of `config/app.py` — the `Storage` facade boots automatically when the key
is there.

### Storage configuration

```python
# config/app.py
from forgeapi import env

config = {
    "storage": {
        "driver": "local",        # "local" | "s3"
        "root": "storage/app",    # local: filesystem root
        "base_url": "/storage",   # local: public URL prefix
    },
}
```

Install the storage extras when needed:

```bash
pip install forge-kits[s3]       # S3 / MinIO / Cloudflare R2
pip install forge-kits[images]   # ImageProcessor (Pillow)
```

### Storage basic operations

```python
from forgeapi import Storage

# write
path = await Storage.put("avatars/user-1.jpg", image_bytes)

# read
data: bytes | None = await Storage.get("avatars/user-1.jpg")

# check / delete
exists: bool = await Storage.exists("avatars/user-1.jpg")
await Storage.delete("avatars/user-1.jpg")

# list
files: list[str] = await Storage.list("avatars/")

# public URL
url: str = Storage.url("avatars/user-1.jpg")   # "/storage/avatars/user-1.jpg"
```

`put()` returns the stored path. `get()` returns `None` when the file is
missing. All file I/O is non-blocking (`asyncio.to_thread`).

### Multiple disks

```python
from forgeapi.storage import LocalDriver, S3Driver

Storage.add_disk("public", LocalDriver(root="public/", base_url="/public"))
Storage.add_disk("backups", S3Driver(bucket="my-backups", region="eu-central-1",
                                     access_key="...", secret_key="..."))

# switch disk
await Storage.disk("backups").put("dump.sql.gz", data)
url = Storage.disk("public").url("logo.png")
```

### S3 / S3-compatible

```python
# config/app.py
from forgeapi import env

config = {
    "storage": {
        "driver": "s3",
        "bucket": "my-bucket",
        "region": "eu-central-1",
        "access_key": env("AWS_ACCESS_KEY_ID"),
        "secret_key": env("AWS_SECRET_ACCESS_KEY"),
        # MinIO / Cloudflare R2:
        # "endpoint_url": env("S3_ENDPOINT_URL"),
        # "acl": "public-read",
    },
}
```

`endpoint_url` makes it work with MinIO, Cloudflare R2, or any S3-compatible
service — same API, different endpoint.

### ImageProcessor

Fluent image pipeline built on Pillow. Install: `pip install forge-kits[images]`

```python
from forgeapi import ImageProcessor

# from raw bytes
pipeline = ImageProcessor.process(raw_bytes)

# from FastAPI UploadFile
pipeline = await ImageProcessor.from_upload(upload_file)

# transform
pipeline = (
    pipeline
    .resize(800, 600)           # fit into 800×600 (preserves ratio)
    .resize(800, 600, crop=True)# crop-fill to exact dimensions
    .thumbnail(256)             # shrink to 256px max side
    .quality(85)                # JPEG quality
    .convert("WEBP")            # format conversion
    .grayscale()                # desaturate
)

# get bytes
data: bytes = pipeline.to_bytes()

# store directly to Storage (returns stored path)
path = await pipeline.store("avatars/user-1", extension="webp")
path = await pipeline.store(directory="thumbs", extension="jpg")
path = await pipeline.store("hero.jpg", disk="public")
```

Pillow is imported lazily — `ImportError` with a clear hint if not installed.

---

## 15. Support

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
Time.now()                            # datetime in server's local timezone
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

## 16. Logger

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

## 17. Middleware

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
# config/app.py
from app.middleware import TimingMiddleware, TenantMiddleware
config = {
    "http": {
        "middleware": [
            TimingMiddleware,
            (TenantMiddleware, {"default_tenant": "acme"}),   # (cls, kwargs) tuple
        ],
    },
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

All configured in the `"http"` key of `config/app.py`:

```python
# config/app.py
config = {
    "http": {
        "cors": ["*"],        # True → all origins; list → specific; False → off
        "rate_limit": 60,     # req/min per IP; True → 60; False → off
        "request_id": True,   # inject X-Request-ID header
        "access_log": True,   # log method/path/status/duration per request
        "middleware": [],     # custom classes or (cls, kwargs) tuples
    },
}
```

| Key | Default | Description |
|---|---|---|
| `cors` | `False` | `True` = allow all; list = specific origins |
| `rate_limit` | `False` | Sliding window per IP — returns `429` with `Retry-After` |
| `request_id` | `False` | Injects `X-Request-ID` header; access via `request.state.request_id` |
| `access_log` | `True` | Logs method, path, status, duration |

---

## 18. Settings

`BaseAppSettings` wraps `pydantic-settings` with `.env` file loading:

```python
from forgeapi.settings import BaseAppSettings

class Settings(BaseAppSettings):
    database_url: str
    redis_url: str | None = None
    cookie_secret: str
    debug: bool = False

settings = Settings()   # reads .env automatically
```

Sensitive field masking — fields containing `password`, `secret`, `token`, `key`, `auth`, `credential` show `***` in `repr`:

```python
>>> print(settings)
Settings(database_url='postgresql://...', cookie_secret='***', debug=True)
```

---

## 19. Seeders

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

**`db:seed` (no arguments) requires `__init__.py` with `__all__`**

`database/seeds/__init__.py` must exist and define `__all__` — without it nothing runs. The list also controls execution order, so put seeders with dependencies first:

```python
# database/seeds/__init__.py
from .role_seeder import RoleSeeder
from .user_seeder import UserSeeder
from .post_seeder import PostSeeder

__all__ = [
    "RoleSeeder",    # must run before UserSeeder
    "UserSeeder",
    "PostSeeder",
]
```

---

## 20. Scheduler

DB-backed task scheduler —  Jobs are defined in code (`schedule.py`);
state (next run time, last status, errors) is persisted in the `scheduled_tasks` table via Tortoise.
No external queue or APScheduler dependency required.

```bash
pip install forge-kits   # Scheduler is included in the base package
```

### Setup

Add `forgeapi.scheduling.models` to the models list in `config/database.py` so Tortoise
creates the `scheduled_tasks` table automatically:

```python
# config/database.py
TORTOISE_ORM = {
    "connections": {...},
    "apps": {
        "models": {
            "models": [
                "database.models",
                "forgeapi.scheduling.models",        # ← add this
                "forgeapi.permissions.models",
            ],
            ...
        }
    },
}
```

If you use the CLI (`schedule:work` / `schedule:run`), the table is created
automatically via `generate_schemas(safe=True)` — no manual migration step needed.

### schedule.py

`forgeapi init` creates a `schedule.py` at the project root. Define all jobs there:

```python
# schedule.py
from forgeapi import Scheduler

scheduler = Scheduler()

scheduler.call(send_daily_report).daily_at("09:00").name("newsletter")
scheduler.call(cleanup_temp_files).every(30).name("cleanup")
scheduler.call(weekly_backup).weekly_on("sunday", at="03:00").name("backup")
scheduler.call(sync_rates).hourly().name("sync-rates")
scheduler.call(health_ping).every_minute().name("health")
```

All callables — sync or async — are accepted:

```python
async def send_daily_report():
    users = await User.filter(newsletter=True).all()
    ...
```

### Timing methods

**Timezone:** schedules run in `timezone` from `config/app.py` (e.g. `env("APP_TIMEZONE", "Europe/Sofia")`),
or `Scheduler(timezone="Europe/Sofia")`. Without either, the server's local time is used.
Stored `next_run_at` / `last_run_at` are wall-clock times in that timezone, so changing it shifts existing schedules.
Daylight saving is not compensated: a job scheduled in an hour that does not exist runs right after the clock jumps.


| Method | When it runs |
|---|---|
| `.every_minute()` | Every minute |
| `.every(n)` | Every *n* minutes |
| `.hourly()` | Every hour |
| `.every_hours(n)` | Every *n* hours |
| `.daily()` | Daily at midnight |
| `.daily_at("HH:MM")` | Daily at the given time |
| `.weekly()` | Every Monday at midnight |
| `.weekly_on("day", at="HH:MM")` | Named weekday at the given time |
| `.monthly()` | 1st of every month, midnight |
| `.monthly_on(day, at="HH:MM")` | Given day of month (31 clamps to the last day) |
| `.yearly()` | Every Jan 1, midnight |
| `.yearly_on(month, day, at="HH:MM")` | Every year on the given date |
| `.every_two_years(month, day, at="HH:MM")` | Every 2 years on the given date |
| `.cron("m h dom mon dow")` | Standard 5-field cron: `*/5 * * * *`, `0 9 * * mon-fri` |
| `.without_overlapping(expires_after=1440)` | Skip a run while the previous one is still running (stale lock ignored after `expires_after` minutes) |

`.name("label")` sets the unique key used in the DB and in CLI commands.
Defaults to the function name.

**Overlapping:** by default a slow job can start again while the previous run is still going (the next slot is claimed before the job runs). Add `.without_overlapping()` to skip those slots instead. The lock lives in `scheduled_tasks.running_since`, so it works across several scheduler instances. A skipped slot is not made up later. If a process crashes mid-run, the lock expires after `expires_after` minutes (default 24h): set it above the job's longest runtime. `schedule:run <name>` refuses to start a job that is locked.

### Running via CLI

```bash
# Run due tasks once — use from cron (every minute)
forgeapi schedule:run

# Run a specific task manually, regardless of schedule
forgeapi schedule:run newsletter

# Start infinite dev loop — checks for due tasks, sleeps until next run
forgeapi schedule:work

# Show all registered tasks and their DB state
forgeapi schedule:list
```

`schedule:work` is the recommended dev runner. For production, add a cron job:

```cron
* * * * * cd /path/to/project && forgeapi schedule:run >> /var/log/scheduler.log 2>&1
```

### In-process with Core (config-driven)

Add a `"scheduler"` key to `config/app.py` — `Core(app)` starts the scheduler as a background task on startup and cancels it on shutdown. No lifespan boilerplate needed.

```python
# config/app.py
config = {
    "scheduler": {
        "schedule": "schedule.py",   # path to your schedule.py
    },
}
```

```python
# main.py — scheduler starts automatically
from fastapi import FastAPI
from forgeapi import Core

app = FastAPI()
core = Core(app)
```

### Manual lifespan (without Core)

If you need to run the scheduler in-process without using the `"scheduler"` key:

```python
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from schedule import scheduler   # your schedule.py

@asynccontextmanager
async def lifespan(app):
    task = asyncio.create_task(scheduler.run())
    yield
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)

app = FastAPI(lifespan=lifespan)
```

`scheduler.run()` calls `sync()` on startup (upserts all jobs to DB), then loops
indefinitely — sleeping until the soonest scheduled task, then calling `run_due()`.

### ScheduledTask model

The `scheduled_tasks` table columns:

| Column | Type | Description |
|---|---|---|
| `name` | `VARCHAR(255)` unique | Job name (`.name("label")`) |
| `schedule_type` | `VARCHAR(20)` | `"interval"` / `"daily"` / `"weekly"` / `"monthly"` / `"yearly"` / `"cron"` |
| `schedule_config` | `JSON` | Schedule parameters (e.g. `{"minutes": 30}`) |
| `is_enabled` | `BOOLEAN` | Toggle without removing from code |
| `next_run_at` | `DATETIME` | When the job will next run |
| `last_run_at` | `DATETIME` | When it last ran |
| `last_status` | `VARCHAR(20)` | `"success"` / `"failed"` |
| `last_error` | `TEXT` | Exception message on failure |
| `running_since` | `DATETIME` null | Set while a `without_overlapping()` job runs. **Added later: existing projects need a migration** (`db:makemigrations && db:migrate`) |

---

## 21. Queue

DB-backed async job queue. Jobs are stored in the `queued_jobs` table; permanently-failed ones land in `failed_jobs`. No external broker — Tortoise ORM only.

### Setup

Add `forgeapi.queue.models` to TORTOISE_ORM so the tables are created:

```python
# config/database.py
TORTOISE_ORM = {
    "apps": {
        "models": {
            "models": ["database.models", "forgeapi.queue.models"],
            ...
        }
    },
}
```

The CLI creates tables automatically via `generate_schemas(safe=True)` — no manual migration step needed.

### Defining a job

```python
from forgeapi.queue import Job

class SendWelcomeEmail(Job):
    queue = "default"   # optional — queue name
    max_tries = 3       # optional — retry attempts before moving to failed_jobs

    def __init__(self, user_id: int):
        self.user_id = user_id

    async def handle(self) -> None:
        user = await User.get(id=self.user_id)
        await mailer.send(user.email, "Welcome!")
```

### Dispatching

```python
from forgeapi.queue import dispatch

await dispatch(SendWelcomeEmail(user_id=user.id))             # immediate
await dispatch(SendWelcomeEmail(user_id=user.id), delay=60)   # available after 60 s
await dispatch(SendWelcomeEmail(user_id=user.id), queue="high")  # override queue
```

### Running the worker

**CLI (recommended for production):**

```bash
forgeapi queue:work        # start infinite worker loop (press Ctrl+C to stop), see --queue below
forgeapi queue:run         # process all currently pending jobs once (use from cron)
```

A worker only processes the queue(s) it is told to. A Job goes to the queue named in its `queue` attribute (default `"default"`), so start a worker per queue:

```bash
forgeapi queue:work                        # queue from the "queue" key of config/app.py, default "default"
forgeapi queue:work --queue=emails         # only "emails"
forgeapi queue:work --queue=high,default   # several; earlier ones are drained first
forgeapi queue:run --queue=emails
```

**In-process with Core (config-driven):**

Add a `"queue"` key to `config/app.py` — `Core(app)` starts the queue worker as a background task on startup.

```python
# config/app.py
config = {
    "queue": {
        "queue": "default",   # queue name to consume
    },
}
```

```python
# main.py — worker starts automatically
from fastapi import FastAPI
from forgeapi import Core

app = FastAPI()
core = Core(app)
```

**Manual lifespan (without Core):**

```python
import asyncio
from contextlib import asynccontextmanager
from forgeapi.queue import Queue

@asynccontextmanager
async def lifespan(app):
    task = asyncio.create_task(Queue().work())
    yield
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
```

**Timezone:** `available_at` and retry delays use `timezone` from `config/app.py`
(or `Queue(timezone="Europe/Sofia")`); without either, the server's local time.
Pending jobs keep their stored `available_at` when the timezone changes.

### Stuck jobs

A job reserved by a worker that then dies (crash, `kill -9`, deploy) is picked up again once its reservation is older than `retry_after` seconds (the `"queue"` section of `config/app.py`, default 300; or `Queue(retry_after=...)`). Each pickup counts as an attempt. If all `max_tries` were used up this way, the job moves to `failed_jobs` without running again (`MaxAttemptsExceeded`) and `failed()` is called.

Set `retry_after` above your slowest job's runtime, otherwise a long job still running may be started a second time by another worker.

### Failed hook

Override `failed()` to react when a job has used up `max_tries` and moved to `failed_jobs`:

```python
class SendWelcomeEmail(Job):
    failed_timeout = 30   # seconds, default 30

    async def failed(self, exception: BaseException) -> None:
        await telegram.send(f"{type(self).__name__} failed: {exception}")
```

- Runs in the background: it never delays the worker. After `failed_timeout` seconds it is cancelled and logged. An exception inside it is only logged.
- `def failed(...)` (sync) also works and runs in a thread.
- Every permanent failure is also logged to the `forgeapi.queue.failed` logger (job class, queue, attempts, error), with or without a hook.
- If the job class can't be imported, `failed()` is skipped (only the log line is written); the job still lands in `failed_jobs`.
- `queue:run` waits for pending hooks before exiting; stopping `queue:work` cancels unfinished ones.

### Failed jobs

After `max_tries` attempts (with exponential backoff), the job is moved to `failed_jobs`.

```bash
forgeapi queue:failed           # list failed jobs
forgeapi queue:retry <id>       # move a failed job back to the queue
forgeapi queue:flush            # delete all failed jobs
```

### DB tables

| Table | Description |
|---|---|
| `queued_jobs` | Pending/reserved jobs (queue, payload, attempts, reserved_at, available_at) |
| `failed_jobs` | Permanently failed jobs (queue, payload, exception, failed_at) |

---

## 22. Mail

Sending e-mail through a `Mailable` class: one class per kind of message, its HTML and text templates next to it.

```python
from forgeapi import Mail, Mailable
```

### Quick start

```bash
forgeapi make:mail Welcome        # app/mail/welcome.py + app/templates/mail/welcome.{html,txt}
```

```python
# app/mail/welcome.py
from forgeapi import Mailable


class Welcome(Mailable):
    subject = "Welcome!"
    template = "welcome.html"
    text_template = "welcome.txt"

    def __init__(self, name: str) -> None:
        self.name = name
```

```html
<!-- app/templates/mail/welcome.html -->
<h1>Hi {{ name }}</h1>
```

```python
from forgeapi import Mail
from app.mail.welcome import Welcome

await Mail.send(Welcome("Ana"), to="ana@example.com")      # now
await Mail.queue(Welcome("Ana"), to="ana@example.com")     # later, by the queue worker
```

With the default `log` driver nothing is sent: the message is written to the log (set `debug` to `True` in `config/app.py` to see it). Switch to `smtp` when you are ready, see [Drivers](#drivers).

### Mail configuration

Mail boots when `config/app.py` has a `"mail"` key (`forgeapi init` adds it).

```python
# config/app.py
from forgeapi import env

config = {
    "mail": {
        "driver": "log",                          # "log" | "smtp"
        "from_address": "noreply@example.com",
        "from_name": "My App",
        "templates": "app/templates/mail",        # Jinja2 templates directory
        "smtp": {
            "host": env("MAIL_HOST", "localhost"),
            "port": 587,
            "username": env("MAIL_USERNAME", ""),
            "password": env("MAIL_PASSWORD", ""),
            "encryption": "starttls",             # "starttls" | "ssl" | None
            "timeout": 30,
        },
    },
}
```

| Key | Default | Meaning |
|---|---|---|
| `driver` | `"log"` | `"log"` writes the message to the log, `"smtp"` sends it. Any other value fails at startup. |
| `from_address` | `""` | Sender address. **Required for sending**: without it (here or on the Mailable) sending raises an error. |
| `from_name` | `""` | Display name next to the address: `My App <noreply@example.com>`. |
| `templates` | `"app/templates/mail"` | Directory with the Jinja2 templates, relative to the project root. |
| `smtp.host` / `smtp.port` | `"localhost"` / `587` | The SMTP server. |
| `smtp.username` / `smtp.password` | `""` | Login. Empty means no authentication. |
| `smtp.encryption` | `"starttls"` | `"starttls"` (usually port 587), `"ssl"` (usually port 465) or `None` (plain, only for a local relay). Any other value fails when the config is loaded. |
| `smtp.timeout` | `30` | Seconds to wait for the server. |

Keep credentials in `.env` and read them with `env(...)`, not in the file.

### Mailable

A Mailable describes one message. All class attributes are optional except that the message needs a body, so set `template`, `text_template`, `html` or `text`.

| Attribute | Meaning |
|---|---|
| `subject` | Subject line. A class attribute, or a `@property` when it depends on the data (`return f"Order #{self.order.id}"`). |
| `template` | HTML template name in the templates directory, e.g. `"welcome.html"`. |
| `text_template` | Plain-text template name, e.g. `"welcome.txt"`. |
| `html`, `text` | Inline body, used exactly as written (**not** rendered as a template). `template` / `text_template` win when both are set. |
| `from_address`, `from_name` | Replace the sender from the `"mail"` section for this message. `from_name = ""` sends without a display name. |
| `reply_to` | `Reply-To` address. Exists only here, there is no config default. |

With both an HTML and a text body the message is `multipart/alternative` (mail clients pick one). With only one of them it is sent as that single type. Sending both is better for deliverability and for clients that block HTML.

Methods:

- `context()` returns the variables for the templates. By default these are the **public instance attributes** (`self.name`, `self.user`, ...), never the class attributes above. Override it to add or compute values:

```python
class Invoice(Mailable):
    subject = "Your invoice"
    template = "invoice.html"

    def __init__(self, order):
        self.order = order

    def context(self) -> dict:
        return {**super().context(), "total": f"{self.order.total:.2f}"}
```

- `attach(filename, content, content_type=None)` attaches bytes. The type is guessed from the file name when omitted. Returns the Mailable, so calls chain.
- `attach_file(path, filename=None)` reads a file from disk and attaches it.

```python
mailable = Invoice(order).attach("invoice.pdf", pdf_bytes).attach_file("terms.pdf")
```

### Templates

- Location: `app/templates/mail/` (the `templates` key). Names are relative to it, subfolders work: `template = "billing/invoice.html"`.
- The directory is resolved from the folder you start the app in, so run the server and the queue worker from the project root.
- Jinja2 syntax. `{% extends %}` and `{% include %}` work inside the directory, which is the way to share one layout:

```html
<!-- app/templates/mail/layout.html -->
<html><body>
  {% block content %}{% endblock %}
  <footer>{{ app_name }}</footer>
</body></html>

<!-- app/templates/mail/welcome.html -->
{% extends "layout.html" %}
{% block content %}<p>Hi {{ name }}</p>{% endblock %}
```

- **Escaping.** `.html`, `.htm` and `.xml` templates are auto-escaped, so `<b>` in a user name is sent as text. `.txt` templates are not escaped.
- **Missing variables fail.** A variable that is not in the context raises an error instead of rendering an empty string, so a half-empty e-mail cannot go out. A missing template raises an error that names the file and the directory.

### Recipients and sender

```python
await Mail.send(mailable, to="a@x.com")
await Mail.send(mailable, to=["a@x.com", "b@x.com"], cc="c@x.com", bcc=["d@x.com"])
```

- `to`, `cc`, `bcc` take one address or a list. At least one recipient is needed.
- Plain addresses only (`ana@example.com`). Do not pass `"Ana <ana@example.com>"`.
- `bcc` recipients receive the message but are not written into its headers.
- The sender is the Mailable's `from_address` if set, otherwise `from_address` from the config.

### Sending and queueing

```python
await Mail.send(Welcome("Ana"), to=email)                              # now
await Mail.queue(Welcome("Ana"), to=email)                             # via the queue worker
await Mail.queue(Welcome("Ana"), to=email, delay=60, queue="mail")     # in 60 s, on the "mail" queue
```

- **`send()`** waits for the driver. If the SMTP server rejects the message or is down, the error is raised in your code: handle it where it matters (a sign-up form probably should not fail because of a welcome e-mail, so use `queue()` there).
- **`queue()`** renders the message **at the call**, then stores plain text/HTML in `queued_jobs` (not the Mailable object). A change to the template after the call does not affect a message already in the queue. It retries like any job (`max_tries = 3`) and lands in `failed_jobs` after that.
- Attachments are stored in the queue table too (base64), so avoid large files in queued mail.
- `queue()` needs the queue tables (`forgeapi.queue.models` in `config/database.py`) and a running worker (`config/queue.py` with the in-app worker, or `forgeapi queue:work`). The worker process reads `config/mail.py` itself.
- A message without a sender, recipients or body, or with a line break in a header or file name (header injection), is rejected **before** it is sent or queued.

### Drivers

**`log`** (default) writes the recipients, subject, attachment names, and both bodies to the `forgeapi.mail` log at INFO level and sends nothing. Use it in development. If `debug` is off, the app logs a warning at startup that mail is only logged, so a forgotten dev setting is noticed in production.

**`smtp`** sends through an SMTP server. It needs the extra package:

```bash
pip install forge-kits[mail]
```

```python
# config/app.py: SMTP with STARTTLS (port 587)
config = {
    "mail": {
        "driver": "smtp",
        "from_address": "noreply@example.com",
        "from_name": "My App",
        "smtp": {"host": env("MAIL_HOST"), "port": 587, "username": env("MAIL_USERNAME"),
                 "password": env("MAIL_PASSWORD"), "encryption": "starttls"},
    },
}
# implicit TLS (port 465): "port": 465, "encryption": "ssl"
```

Without the package, choosing `smtp` fails at startup with `pip install forge-kits[mail]` in the message.

**Before going live**
- `driver` is `"smtp"` and the credentials come from the environment.
- `from_address` is on a domain you control and its DNS (SPF, DKIM) is set up: otherwise providers send the mail to spam. This is outside forge-kits.
- If you use `queue()`, a queue worker is running in production.
- Send a real message to yourself first: the SMTP path is only covered by tests with a fake client.

### Errors

| Message | Cause |
|---|---|
| `Mail is not configured.` | `config/app.py` has no `"mail"` key. |
| `Mail has no sender address.` | No `from_address` in the config or on the Mailable. |
| `Mail has no recipients.` | `to`, `cc` and `bcc` are all empty. |
| `Mail has no body.` | None of `template`, `text_template`, `html`, `text` is set. |
| `Mail headers must not contain line breaks.` | A `\r` or `\n` in the subject, an address, the sender name or an attachment name. |
| `Mail template '...' not found in '...'` | The template name or the `templates` directory is wrong. |
| `'name' is undefined` (Jinja) | The template uses a variable the Mailable does not provide. |
| `Unknown mail driver '...'` | `driver` is not `log` or `smtp`. |
| `The smtp mail driver requires aiosmtplib.` | The `mail` extra is not installed. |

### Generating a mail

```bash
forgeapi make:mail WeeklyReport
```

creates three files and never overwrites an existing one:

```
app/mail/weekly_report.py                  class WeeklyReport(Mailable), subject "Weekly report"
app/templates/mail/weekly_report.html      <h1>Weekly report</h1> and a greeting
app/templates/mail/weekly_report.txt       the plain-text part
```

The generated class takes a `name` argument and the templates use `{{ name }}`: replace both with your own data together, because a template variable the class does not provide fails at send time. If the `"mail"` section of `config/app.py` sets another `templates` directory, the templates go there. `app/mail` and `app/templates/mail` are created on demand, `init` does not create them.

---

## 23. CLI reference

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
forgeapi make:<kind> <Name> [flags]
forgeapi make:mail -h               # help for one generator
```

| Command | Creates | Notes |
|---|---|---|
| `make:controller Post` | `app/controllers/post_controller.py` | `-m` also a model, `-s` also a schema. `AdminUser` becomes `app/controllers/admin/user_controller.py` with prefix `/admin/users`. |
| `make:model Post` | `database/models/post.py`, import added to `database/models/__init__.py` | `-c` controller, `-s` schema, `--alias Worker` writes the class into `worker.py` instead of its own file, so several models can share one file. |
| `make:schema Post` | `app/schemas/post.py` | `PostCreate`, `PostUpdate`, `PostResponse`, fields read from the model, see [Schemas](#9-schemas). `--exclude a,b` drops fields. |
| `make:seed User` | `database/seeds/user_seeder.py` | |
| `make:job SendWelcomeEmail` | `app/jobs/send_welcome_email.py` | A queue `Job`, see [Queue](#21-queue). |
| `make:policy Post` | `app/policies/post_policy.py` | `@gate.policy(Post)`. Imports the model, so create it first. A trailing `Policy` in the name is dropped. |
| `make:factory Post` | `database/factories/post_factory.py` | Test factory, list the values in `definition()`. |
| `make:observer Post` | `app/observers/post_observer.py` | Register it with `Post.observe(PostObserver)`. |
| `make:provider Metrics` | `app/providers/metrics_provider.py` | Add its dotted path to `"providers"` in `config/app.py`. |
| `make:command SendWeeklyReport` | `app/commands/send_weekly_report_command.py` | Runs as `forgeapi send:weekly-report`, see [Custom commands](#custom-commands). |
| `make:mail Welcome` | `app/mail/welcome.py`, `app/templates/mail/welcome.html`, `welcome.txt` | See [Mail](#22-mail). |
| `make:listener OrderCreated` | `app/listeners/order_created_listener.py` | `@broadcast.on("order:created")`. Needs the `"broadcast"` key in `config/app.py`. |

Rules for every generator:

- Run it inside a project (a folder with `config/`). Outside one it writes nothing and says so.
- The name is CamelCase letters and digits, starting with a letter. `SendWeeklyReport` becomes the file `send_weekly_report`.
- An **existing file is never overwritten**: the command prints `exists` and moves on.
- Folders are created when needed (and made packages with `__init__.py`). `forgeapi init` creates only `app/controllers`, `app/schemas` and the `database` folders, so `app/policies`, `app/jobs`, `app/mail`, `app/listeners`, ... appear with the first `make:*` for them.
- Suffixes you type are not doubled: `make:policy PostPolicy` and `make:policy Post` give the same file.

**`make:listener`** derives the event name from the class name: the first CamelCase word, then `:`, the rest joined with `-`. `OrderCreated` is `order:created`, `UserSignedUp` is `user:signed-up`, `Order` is `order`. The function is named `on_<snake_name>` and receives the emitted payload as `data: dict`. If `config/app.py` has no `"broadcast"` key, the command tells you, because listeners are only loaded when it exists.

### Custom commands

`make:command <Name>` generates a `Command` subclass in `app/commands`. Every module there is imported on demand: the command is runnable as `forgeapi <name>`
and listed under "project" in `forgeapi`. The name comes from the class: `SendWeeklyReport` becomes
`send:weekly-report`, `Cleanup` becomes `cleanup`. Names used by built-in commands (`make:*`, `db:*`, ...) are refused
at generation time and skipped (with a warning) at run time.

```python
from forgeapi.cli import ui
from forgeapi.cli.base import Command


class SendWeeklyReportCommand(Command):
    name = "send:weekly-report"
    description = "Email the weekly report"

    def run(self, report_id: int, *emails: str, to: str = "me", dry_run: bool = False) -> None:
        """Email the weekly report."""
        ui.info(f"report {report_id} -> {to}, {len(emails)} extra, dry run: {dry_run}")
```

```bash
forgeapi send:weekly-report 42 a@x.com b@x.com --to bob --dry-run
forgeapi send:weekly-report -h      # usage generated from the signature (and the docstring)
```

The parameters of `run()` are the command line, converted to the declared types. No parsing code is needed:

| In `run()` | On the command line |
|---|---|
| `report_id: int` (no default) | positional argument, `42` |
| `*emails: str` | all remaining positional arguments |
| `to: str = "me"` (has a default) | option, `--to bob` or `--to=bob` (`_` becomes `-`) |
| `dry_run: bool = False` | flag, `--dry-run` (a `True` default is switched off with `--no-name`) |
| `tag: list[str] = ()` | repeatable option, `--tag a --tag b` |
| `*, to: str` (keyword-only, no default) | required option |

`int`, `float`, `str`, `Path` and `X | None` are supported. Bad input (a missing or unknown argument, a value of the wrong type)
prints a one-line error with a hint to `-h` and exits with code 1, `run()` is not called. `--` ends the options, `-5` is a
number, not an option. `-h` and `--help` are always taken by the CLI.

`async def run(...)` is awaited, so models can be queried directly. If you need the raw command line instead, override
`handle(self, cmd, args)`: it receives everything typed after the command name as a list of strings.

A module that fails to import does not hide the other commands: the error is printed as a warning.

### DB commands

> Never run `aerich` directly — always use `forgeapi db:*`

```bash
forgeapi db:init
forgeapi db:makemigrations
forgeapi db:makemigrations -n add_email_field
forgeapi db:migrate
forgeapi db:migrate --force   # DROP every table + migration history, then migrate from scratch (asks confirmation, -y skips)
forgeapi db:downgrade
forgeapi db:history
forgeapi db:seed
forgeapi db:fresh             # TRUNCATE all tables (asks confirmation)
forgeapi db:fresh --force     # DROP all tables (irreversible)
```

### Dev server

> Never use `uvicorn` directly — always use `forgeapi runserver`

```bash
forgeapi runserver                  # with forge-kits[dev]: server + queue worker + scheduler, one terminal. Otherwise only the web server
forgeapi runserver --reload
forgeapi runserver --port 9000 --host 0.0.0.0 --reload
```

#### Dev interface of `runserver`

Runs everything the project needs in development as **separate processes** in one terminal, with a tab for each:

```
  ● server   ● queue   ● schedule   ● logs
 ─────────────────────────────────────────────────────────────────────
  INFO      Uvicorn running on http://127.0.0.1:8000
  INFO      Application startup complete.
  INFO      forgeapi.access  GET /ping → 200 [1.4ms]
```

```bash
pip install forge-kits[dev]         # the tabbed interface (Textual)
forgeapi runserver
```

| Process | Starts when | Command it runs |
|---|---|---|
| `server` | always | `uvicorn <app> --reload` (reload is on, `--no-reload` turns it off) |
| `queue` | `config/app.py` has a `"queue"` key | `forgeapi queue:work` |
| `schedule` | `config/app.py` has a `"scheduler"` key and the schedule file exists | `forgeapi schedule:work` |

The `logs` tab is not a process: it collects what the application and forgeapi log in the server process (broadcast, auth, cache, mail, your own `Log.channel(...)`), so `server` keeps only uvicorn and the HTTP requests (`forgeapi.access`). A line is routed by the name of the logger that wrote it.

**Keys** (tabs and stream)

| Key | Does |
|---|---|
| `Tab`, `Shift+Tab`, `1`–`9` | Next / previous tab, tab by number |
| `r` | Restart the process of the current tab (`logs` restarts the server) |
| `/` | Search: shows only the lines that contain the text (case-insensitive). `Enter` keeps the filter, `Esc` clears it |
| `m` | Switch between tabs and the interleaved stream |
| `t` | Timestamps on / off |
| `c` | Clear the current tab (all tabs in stream mode) |
| `q`, `Ctrl+C` | Stop everything. Press again to force |

Scroll with the mouse or the arrow keys, `PgUp`/`PgDn`. Each tab keeps its last 5000 lines. New output follows the bottom only while you are at the bottom: scroll up to read and it stays put.

The dot before a tab name shows the process state: green running, yellow starting or restarting, red exited or given up, grey stopped.

**How the processes are handled**

- **No double work.** Without the dev interface (Textual not installed) the queue worker and the scheduler run *inside* the web process. In the dev interface they are separate processes and the embedded copies are switched off (the server process gets `FORGEAPI_EXTERNAL_WORKERS=1`), so a job is never executed twice.
- **Start order.** The processes start one after another, each when the previous one reports that it is up (up to 20 s, then the rest start anyway). This avoids several processes creating tables in the same SQLite file at once ("database is locked").
- **Crashes.** A worker that exits on its own is restarted after a growing pause (1 s, 2 s, 4 s, up to 10 s) and the tab says so. After 5 exits within a minute it is given up (red dot) and the tab says `not restarting (press r)`. `r` starts it again. If the `server` itself exits, everything stops and `runserver` exits with the server's code (uvicorn's reloader already survives errors in your code, a server exit means something else is wrong, such as a busy port).
- **Reload.** Code changes reload the **server** only. The queue worker and the scheduler keep the code they started with: press `r` on their tab after changing a job or `schedule.py`.
- **Stopping.** Each process gets the same signal Ctrl+C would send it, so uvicorn and the workers shut down gracefully. A process that does not stop within 5 s is terminated, then killed.
- **One look for every line.** uvicorn, the forgeapi commands and the forgeapi logger print their levels differently. Here each line is shown as `LEVEL message` with the same colours: `DEBUG` grey, `INFO` cyan, `DONE` green, `WARNING` yellow, `ERROR` red. A line without a level (a `print` in your job) is shown with an empty level column.
- **Own processes.** `FORGEAPI_EXTERNAL_WORKERS=1` is also the switch to use when you run `forgeapi queue:work` and `forgeapi schedule:work` yourself (for example as separate services in production): set it for the web process and the embedded copies stay off.

The dev interface is for development. In production run the server, `queue:work` and `schedule:work` (or a cron job for `schedule:run`) under your process manager.

### Scheduler

```bash
forgeapi schedule:run             # run all due tasks once (use from cron)
forgeapi schedule:run <name>      # run a specific task manually
forgeapi schedule:work            # start infinite dev loop
forgeapi schedule:list            # show all tasks and their DB state
```

### Queue

```bash
forgeapi queue:work [--queue=a,b] # start infinite worker loop (queue names; default from the "queue" key of config/app.py)
forgeapi queue:run  [--queue=a,b] # process all pending jobs once (use from cron)
forgeapi queue:failed             # list failed jobs
forgeapi queue:retry <id>         # move a failed job back to the queue
forgeapi queue:flush              # delete all failed jobs
```

### Inspection

```bash
forgeapi routers   # list all registered routes (METHOD, PATH, HANDLER)
forgeapi models    # list all Tortoise model classes, tables, and fields
```

---

## 24. Configuration reference (config/)

The only config format is a **`config/` directory of Python dict files**
Each `config/<section>.py` defines a module-level
`config = {...}`; the filename is the section name. All sections are
optional — `Core(app)` works with no config files at all.
(`forgeapi.toml` is no longer supported — `load_config` raises with a
migration hint.)

### env() helper

```python
from forgeapi import env

env("APP_DEBUG", False)   # reads env var; casts "true"/"false"/"null"
env("COOKIE_SECRET")      # → str | None
```

### Known sections

`config/app.py` holds the project settings at the top level and one key per feature. A feature is on while its key is there, comment the key out to switch it off:

```python
# config/app.py
from forgeapi import env

config = {
    # project
    "name": "my-app",
    "version": "0.1.0",
    "api_prefix": "/api/v1",                 # URL prefix of every controller route
    "debug": env("APP_DEBUG", False),        # verbose forgeapi logging, never in production
    "timezone": env("APP_TIMEZONE", "UTC"),  # IANA name, the scheduler runs in this timezone (default: server local time)
    "providers": [],                         # extra Provider classes / dotted paths

    "http": {
        "cors": ["*"],
        "rate_limit": 60,
        "request_id": True,
        "access_log": True,
        "middleware": [],
    },

    "auth": {                                # see §5 for guard keys
        "default": "api",
        "guards": {
            "api": {"strategy": "cookie",
                    "model": "database.models.user.User",
                    "session_model": "database.models.session.Session"},
        },
    },

    "pagination": {"default_limit": 20, "max_limit": 100},

    "cache": {"driver": "database", "prefix": "", "ttl": None,
              "redis_url": "redis://localhost:6379/0"},

    "storage": {
        "driver": "local",        # "local" | "s3"
        "root": "storage/app",    # local: filesystem root
        "base_url": "/storage",   # local: public URL prefix
        # S3 / MinIO / R2:
        # "bucket": "my-bucket",
        # "region": "us-east-1",
        # "access_key": env("AWS_ACCESS_KEY_ID"),
        # "secret_key": env("AWS_SECRET_ACCESS_KEY"),
        # "endpoint_url": "",     # MinIO / R2 endpoint
        # "acl": "public-read",
    },

    "broadcast": {                           # activates BroadcastProvider (see §7)
        "driver": "redis",          # driver alias, register a custom one with register_driver()
        "driver_options": {
            "url": env("REDIS_URL", "redis://localhost:6379"),
            "namespace": "forge",
            "mode": "pubsub",       # "pubsub" | "stream"
            # stream mode only:
            # "maxlen": None,       # keep last N messages per stream key
            # "group": "backend",   # consumer group name
            # "consumer": "worker-1",
        },
    },

    "mail": {                                # activates MailProvider (see §22)
        "driver": "log",                     # "log" | "smtp"
        "from_address": "noreply@example.com",
        "from_name": "My App",
        "templates": "app/templates/mail",
        # "smtp": {"host": "smtp.example.com", "port": 587, "username": "", "password": "",
        #          "encryption": "starttls"},     # needs forge-kits[mail]
    },

    # opt-in, each needs its models in config/database.py (see §20 and §21)
    # "scheduler": {"schedule": "schedule.py"},   # path to your schedule.py relative to project root
    # "queue": {"queue": "default"},              # queue name the in-process worker will consume
}
```

A top-level key that is neither a project setting nor a dict raises `ForgeAPIConfigError` (a typo such as `"debg"` is caught). Only `config/app.py` and `config/database.py` are read, any other file in `config/` is ignored.

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
    "use_tz": True,
    "timezone": env("APP_TIMEZONE", "UTC"),   # same .env value as config/app.py
    "apps": {
        "models": {
            "models": ["database.models", "forgeapi.cache.models", "forgeapi.permissions.models"],
            "default_connection": "default",
            "migrations": "database.migrations",
        }
    },
}
```

`use_tz` / `timezone` are Tortoise options (defaults: `True` / `"UTC"`). Keep `timezone` in sync with `config/app.py` by reading the same `APP_TIMEZONE` from `.env`. Don't name the variable `TIMEZONE`: Tortoise overwrites `os.environ["TIMEZONE"]` on init.

An explicit `config = {"tortoise_orm": "app.settings.TORTOISE_ORM"}` is only
needed when the dict lives somewhere non-standard.

### Custom sections

Any extra dict key of `config/app.py` becomes a section, reachable with dot access:

```python
# config/app.py
config = {
    # ...
    "services": {"stripe": {"key": env("STRIPE_KEY")}},
}
```

```python
from forgeapi.config import config

config("services.stripe.key")            # from anywhere, no Core object needed
config("services.stripe.key", "")        # with a default for a missing key
config("name")                           # project settings by their plain name
config("auth.guards.api.strategy")       # built-in sections work the same way
config()                                 # the whole KitConfig
```

The config is read once and kept. `Core(app)` hands over the one it loaded, in a script or a worker without `Core` the first call reads `config/`. `config.clear()` forgets it, so the next call reads again (use it in tests). `core.config.get("services.stripe.key", default="")` does the same through the `Core` object.

The function lives in `forgeapi.config`, not in `forgeapi`: a name `forgeapi.config` is the package itself.

Known sections are validated by Pydantic models; misconfiguration raises
`ForgeAPIConfigError` with a hint. Feature enablement is decided by section
**presence**, e.g. auth boots only when `config/app.py` has an `"auth"` key.

---

## 25. MCP Server

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
# Interactive prompt — choose scope on the fly
forgeapi mcp:install

# Per-project — adds to .mcp.json in the current directory
forgeapi mcp:install --project

# Global (user scope) — available in all projects
forgeapi mcp:install --global

# Check current status
forgeapi mcp:status
```

Or use the `claude` CLI directly:

```bash
# Per-project
claude mcp add forge-kits forgeapi-mcp

# Global (user scope)
claude mcp add --scope user forge-kits forgeapi-mcp
```

---

### Global setup for Claude Code (manual)

Install once and use across **all your projects**. Create or edit `~/.claude/.mcp.json`:

**macOS / Linux — `~/.claude/.mcp.json`:**

```json
{
  "mcpServers": {
    "forge-kits": {
      "command": "forgeapi-mcp"
    }
  }
}
```

**Windows — `C:\Users\<your-username>\.claude\.mcp.json`:**

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

> **Tip:** `forgeapi mcp:install --project` generates `.mcp.json` automatically with the correct path for your current venv.

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
| `project_info(path)` | List project files and structure |

#### get_docs topics

| Topic | Content |
|---|---|
| `cheatsheet` | Controller + queries + auth + events quick reference |
| `workflow` | CLI rules — which commands to use and which to avoid |
| `core` | Core constructor, options, startup sequence |
| `controllers` | Controller, @route, schema class var, auto-prefix |
| `events` | BroadcastManager, pub/sub, Streams, cross-project |
| `auth` | Guards, CurrentUser, strategies (cookie/telegram), session ops |
| `permissions` | PermissionsMixin, require_permission, roles |
| `policies` | Policy, Gate, authorize, allows, discover |
| `pagination` | QuerySet .paginate(), offset, cursor, configuration |
| `schemas` | Create / Update / Response schemas, Schema.partial, make:schema |
| `middleware` | Middleware, Guard, built-in middleware |
| `cli` | All CLI commands reference |
| `config` | config/ directory format, all known sections |
| `models` | ModelMixin, @scope, Tortoise field types |
| `cache` | Cache facade, drivers, remember/pull/increment |
| `storage` | Storage facade, LocalDriver, S3Driver, ImageProcessor |
| `scheduler` | Scheduler, timing methods, lifespan integration |
| `queue` | Job, dispatch, Queue worker, CLI commands |
| `scopes` | @scope decorator, queryset chaining |
| `observers` | ModelObserver, lifecycle hooks |
| `support` | Number, Str, Time helpers |
| `tortoise` | Basic CRUD, filter, order, async gather |
| `tortoise_advanced` | Q objects, prefetch_related, transactions, raw SQL |

#### get_example patterns

| Pattern | Content |
|---|---|
| `crud_controller` | Full CRUD with ModelMixin + schema class var |
| `broadcasting_pubsub` | BroadcastManager pub/sub mode |
| `broadcasting_stream` | BroadcastManager stream mode (persistent) |
| `rbac` | Full RBAC — model, seeder, protected routes |
| `pagination` | QuerySet .paginate() with filters |
| `guard` | API key, active-user guards |
| `cache` | remember, pull, counters in a controller |
| `scheduler` | lifespan task worker with daily/weekly jobs |
| `queue` | Job definition, dispatch, worker, CLI |

#### generate_controller

```
generate_controller("Post", ["GET /", "POST /", "GET /{id}", "PATCH /{id}", "DELETE /{id}"])
```

#### scan_project

```
scan_project(".")
```

Returns a structured report of all models, controllers, schemas, events, listeners, seeders, pyproject.toml dependencies, and .env keys (values hidden). Call this at the start of every session on a forge-kits project.

---

## 26. Testing

Tests are plain pytest. forge-kits adds only [factories](#factories) (`pip install forge-kits[dev]` for Faker).

A factory needs a database, so a test sets one up the usual pytest way, in `tests/conftest.py`:

```python
import pytest
from tortoise import Tortoise


@pytest.fixture
async def db():
    await Tortoise.init(db_url="sqlite://:memory:", modules={"models": ["database.models"]})
    await Tortoise.generate_schemas()
    yield
    await Tortoise.close_connections()
```

```python
async def test_user_is_saved(db):
    user = await UserFactory.create(name="Ann")

    assert await User.filter(name="Ann").exists()
```
