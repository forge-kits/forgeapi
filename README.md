# ForgeAPI — Documentation

## Table of Contents

1. [Quick start](#1-quick-start)
2. [Project structure](#2-project-structure)
3. [Core](#3-core)
4. [Exceptions](#4-exceptions)
5. [Auth](#5-auth)
   - [How it works](#how-it-works)
   - [CurrentUser and OptionalUser](#currentuser-and-optionaluser)
   - [JWT strategy](#jwt-strategy)
   - [Cookie strategy](#cookie-strategy)
   - [Telegram strategy](#telegram-strategy)
6. [Pagination](#6-pagination)
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
   - [RedisBus — cross-project bridge](#redisbus--cross-project-bridge)
   - [Testing events](#testing-events)
8. [Controllers](#8-controllers)
   - [Base pattern](#base-pattern)
   - [Route decorator](#route-decorator)
   - [Auto-prefix and namespace](#auto-prefix-and-namespace)
9. [Schemas](#9-schemas)
   - [Base classes](#base-classes)
   - [Schema directories](#schema-directories)
   - [generate:schema](#generateschema)
10. [Permissions](#10-permissions)
    - [Setup](#setup)
    - [PermissionsMixin](#permissionsmixin)
    - [Dependencies](#dependencies)
    - [Role and Permission models](#role-and-permission-models)
11. [Middleware](#11-middleware)
    - [CORS](#cors)
    - [Rate limiting](#rate-limiting)
    - [Request ID](#request-id)
    - [Access logging](#access-logging)
12. [Settings](#12-settings)
13. [Seeders](#13-seeders)
14. [CLI reference](#14-cli-reference)
15. [forgeapi.toml reference](#15-forgeapitoml-reference)
16. [Telescope](#16-telescope)
    - [What Telescope captures](#what-telescope-captures)
    - [WebSocket live stream](#websocket-live-stream)
    - [Sensitive data masking](#sensitive-data-masking)
    - [Recording jobs](#recording-jobs)
17. [MCP Server](#17-mcp-server)

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
| `full-asyncpg` | auth + asyncpg | PostgreSQL + JWT |
| `full-aiosqlite` | auth + aiosqlite | SQLite + JWT |
| `full-aiomysql` | auth + aiomysql | MySQL + JWT |
| `full` | auth + all three drivers | everything |
| `mcp` | `mcp` | forge-kits MCP server for AI-assisted development |

```bash
pip install forge-kits[full-asyncpg]   # PostgreSQL + JWT
pip install forge-kits[mcp]            # MCP server
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
| `debug` | `bool` | `False` | Debug mode — enables Telescope + relaxes security checks. **Never use in production.** |
| `config_path` | `str` | `"forgeapi.toml"` | Path to the TOML config file |

### permissions=True — auto-detection

When `permissions=True`, Core scans `models_dir` for a class that inherits `PermissionsMixin` and registers it automatically. No need to import the model in `main.py`.

```python
# Auto — scans models_dir, finds User (or any PermissionsMixin subclass)
core = Core(app, auth=True, permissions=True)

# Explicit — use when you have multiple PermissionsMixin models
from database.models import User
core = Core(app, auth=True, permissions=User)
```

If zero models are found → `ForgeAPIConfigError` with a hint.  
If more than one model is found → `ForgeAPIConfigError` listing the models — pass explicitly.

### Debug mode

```python
core = Core(app, auth="telegram", debug=True)
```

`debug=True` disables security checks that are inconvenient during development:

| Component | Normal | Debug |
|---|---|---|
| Telegram `auth_date` | Rejected if older than 24 h | Skipped — any age accepted |

All debug activity is logged as `WARNING` so it's visible in the console even without configuring log levels. **Never use `debug=True` in production.**

---

### Accessing after setup

```python
core.auth       # → AuthBackend | None
core.config     # → KitConfig (parsed forgeapi.toml)
```

### Including routers manually

```python
core.include_router(admin_router)                    # prefix: /api/v1
core.include_router(admin_router, prefix="/admin")   # prefix: /api/v1/admin
```

---

## 4. Exceptions

ForgeAPI uses a typed exception hierarchy so you can catch errors precisely.

```python
from forgeapi import ForgeAPIError, ForgeAPIConfigError, ForgeAPIImportError
```

| Class | Inherits | When raised |
|---|---|---|
| `ForgeAPIError` | `Exception` | Base — all ForgeAPI errors |
| `ForgeAPIConfigError` | `ForgeAPIError` | Misconfiguration: missing secret, unknown strategy, model not found |
| `ForgeAPIImportError` | `ForgeAPIError`, `ImportError` | Optional dependency not installed |

Every exception includes a `hint` field with a fix suggestion. The hint is appended to the message automatically:

```
ForgeAPIConfigError: Auth backend is not configured.
  Hint: Enable auth in Core: Core(app, auth=True).
```

### Catching examples

```python
from forgeapi import ForgeAPIConfigError, ForgeAPIImportError

# Catch a specific error
try:
    core = Core(app, auth=True)
except ForgeAPIConfigError as e:
    print(e)        # full message + hint
    print(e.hint)   # just the hint string

# ForgeAPIImportError is also an ImportError — existing except clauses still work
try:
    from forgeapi.auth.strategies.jwt import JWTStrategy
except ImportError as e:
    print("missing dep:", e)
```

### When each error is raised

**`ForgeAPIConfigError`**

| Trigger | Message |
|---|---|
| `Core(app, auth=True)` without JWT_SECRET set | `JWT secret key is not set.` |
| `Core(app, auth="unknown")` | `Unknown auth strategy 'unknown'.` |
| `Core(app, permissions=True)` — no PermissionsMixin model found | `No model with PermissionsMixin found in '…'.` |
| `Core(app, permissions=True)` — multiple PermissionsMixin models | `Multiple PermissionsMixin models found: User, Team.` |
| `forgeapi.auth.auth.<method>` called before `Core(app, auth=True)` | `Auth backend is not configured.` |
| `RequirePermission` / `RequireRole` used before `permissions=` set | `User model not registered.` |
| `COOKIE_SECRET` env var missing for CookieStrategy | `Cookie secret key is not set.` |

**`ForgeAPIImportError`**

| Trigger | Message |
|---|---|
| `Core(app, auth=True)` without PyJWT installed | `Auth backend could not be loaded.` |
| `JWTStrategy` imported without PyJWT | `JWTStrategy requires PyJWT.` |

---

## 5. Auth

### How it works

Strategy pattern — three built-ins: JWT, Cookie, Telegram. Pick one in `forgeapi.toml`.

When `Core(app, auth=True)` runs:
1. Strategy is built from config / env vars.
2. `AuthBackend` is registered as a global singleton.
3. `CurrentUser` and `OptionalUser` become live FastAPI dependencies.

### CurrentUser and OptionalUser

```python
from forgeapi.auth import CurrentUser, OptionalUser
```

**`CurrentUser`** — required auth. Returns `AuthUser` or raises `401`.

```python
@route.get("/me")
async def me(self, user: CurrentUser):
    return {"id": user.id, "username": user.username}
```

**`OptionalUser`** — returns `AuthUser` if credentials are present, `None` otherwise. Never raises 401.

```python
@route.get("/feed")
async def feed(self, user: OptionalUser):
    return personalised_feed(user.id) if user else public_feed()
```

### AuthUser fields

| Field | Type | Description |
|---|---|---|
| `user.id` | `Any` | JWT/Cookie: value of `sub` claim (string). Telegram: `telegram_id` (int). |
| `user.username` | `str \| None` | Username from token / initData |
| `user.auth_method` | `str` | `"jwt"` / `"cookie"` / `"telegram"` |
| `user.extra` | `dict` | Extra claims not in standard fields |

> JWT `user.id` is always a **string**. Cast when needed: `int(user.id)`.

---

### JWT strategy

Reads from `Authorization: Bearer <token>`.

```toml
[auth]
strategy            = "jwt"
jwt_secret_env      = "JWT_SECRET"    # env var name
access_ttl_minutes  = 30
refresh_ttl_days    = 7
```

```python
from forgeapi.auth.backend import _global_backend

strategy = _global_backend.strategy   # JWTStrategy

# issue tokens
access  = strategy.create_access_token({"sub": str(user.id), "username": user.username})
refresh = strategy.create_refresh_token({"sub": str(user.id)})

# decode manually
payload = strategy.decode(token)      # raises 401 on invalid/expired
```

Extra claims land in `user.extra`:

```python
token = strategy.create_access_token({"sub": "42", "username": "alice", "role": "admin"})
# in a route:
user.extra["role"]  # → "admin"
```

---

### Cookie strategy

Stores a signed JSON session in an `HttpOnly` cookie.

```toml
[auth]
strategy        = "cookie"
cookie_name     = "session"
cookie_httponly = true
cookie_secure   = false    # set true in production
```

```python
from forgeapi.auth.backend import _global_backend
from fastapi import Response

strategy = _global_backend.strategy   # CookieStrategy

# login
strategy.set_cookie(response, {"sub": str(user.id), "username": user.username})

# logout
strategy.delete_cookie(response)
```

Cookie is signed with HMAC-SHA256. Invalid signature → `401`. Secret from `COOKIE_SECRET` env var.

---

### Telegram strategy

Validates `initData` from Telegram Mini App. No login endpoint needed — auth happens on every request.

```toml
[auth]
strategy = "telegram"
```

```bash
# single bot
BOT_TOKEN=123456:ABC-your-token

# multiple bots — comma-separated, no spaces required
BOT_TOKEN=123456:ABC-bot-one,789012:DEF-bot-two
```

Client sends `window.Telegram.WebApp.initData` in:
- `X-Telegram-Init-Data: <initData>` header (preferred)
- `Authorization: tma <initData>` header

```python
async def me(self, user: CurrentUser):
    user.id           # telegram_id (int)
    user.username     # @username or None
    user.extra        # {"first_name": ..., "last_name": ..., "language_code": ..., "auth_date": ...}
```

Manual validation (e.g. webhooks):

```python
from forgeapi.auth.backend import _global_backend

tg_user = _global_backend.strategy.validate_init_data(raw_init_data_string)
```

---

## 6. Pagination

Inject `Pagination` as a dependency — reads `?page` and `?limit` from the query string.

```python
from forgeapi.pagination import Pagination

@route.get("/posts")
async def list_posts(self, pagination: Pagination) -> dict:
    total = await Post.all().count()
    items = await Post.all().offset(pagination.offset).limit(pagination.limit)
    return {"items": items, "total": total, "page": pagination.page, "limit": pagination.limit}
```

| Attribute | Description |
|---|---|
| `pagination.page` | Current page (1-based) |
| `pagination.limit` | Items per page (capped at `max_limit`) |
| `pagination.offset` | SQL offset = `(page - 1) * limit` |

### Query parameter validation

FastAPI enforces these constraints automatically and returns `422` on violation:

| Parameter | Constraint | Default |
|---|---|---|
| `?page` | Integer, 1 ≤ page ≤ 10 000 | `1` |
| `?limit` | Integer ≥ 1 | `default_limit` from config |

`?limit` values above `max_limit` are silently clamped — no error is raised.

### Configuration

```toml
[pagination]
default_limit = 20
max_limit     = 100
```

Via `Core`:

```python
Core(app, pagination=20)    # default_limit=20, max_limit from toml
Core(app, pagination=True)  # both from toml
```

Via `Paginator.configure()` directly (useful outside `Core`):

```python
from forgeapi.pagination import Paginator

Paginator.configure(default_limit=10, max_limit=50)
```

`configure()` raises `ValueError` if `default_limit < 1`, `max_limit < 1`, or `default_limit > max_limit`.

---

## 7. Events

Events decouple side effects (emails, notifications, cache invalidation, analytics) from business logic. Instead of calling three different services inside a route handler, dispatch one event and let registered listeners handle everything independently.

### Lifecycle overview

```
route handler
    │
    └─ await event.dispatch()
              │
              ├─ background=False → asyncio.gather(all listeners) → await → continue
              │
              ├─ background=True  → asyncio.create_task(gather) → continue immediately
              │
              └─ redis=True       → publish to Redis channel
                                         │
                                   each worker's subscriber
                                         │
                                   (ttl set?) → SET NX EX {ttl} → only first worker continues
                                         │
                                   asyncio.gather(all local listeners)
```

### Defining events

```python
# app/events/order_created_event.py
from forgeapi import Event

class OrderCreated(Event):
    background = True        # True = fire-and-forget; False = await before response
    redis      = False       # True = publish to Redis (multi-worker distribution)
    redis_type = "pubsub"    # "pubsub" = fan-out to all workers | "stream" = persistent, consumer groups
    namespace  = "forgeapi:events"  # Redis key prefix: {namespace}:{ClassName}
    ttl: int | None = None   # Redis dedup window in seconds; None = no dedup

    def __init__(self, order_id: int, total: float) -> None:
        self.order_id = order_id
        self.total    = total
```

#### Class-level flags

| Flag | Default | Effect |
|---|---|---|
| `background` | `False` | `False` — `dispatch()` awaits all listeners before returning. `True` — listeners are `create_task`-ed, the caller continues immediately |
| `redis` | `False` | `True` — event is serialised and published to Redis |
| `redis_type` | `"pubsub"` | `"pubsub"` — fan-out via Redis Pub/Sub (`PUBLISH`); `"stream"` — persistent delivery via Redis Streams (`XADD`) with consumer groups |
| `namespace` | `"forgeapi:events"` | Redis key prefix. Pub/sub channel: `{namespace}:{ClassName}`. Stream key: `{namespace}:{ClassName}` |
| `ttl` | `None` | Dedup window in seconds (pub/sub only). Only the first worker that wins `SET NX EX {ttl}` on `event_id` processes the event |

Combinations:

| `background` | `redis` | Behaviour |
|---|---|---|
| `False` | `False` | Default: await listeners, then return the response |
| `True` | `False` | Fire-and-forget: schedule listeners in background, return response now |
| `True` | `True` | Publish to Redis (fast), each worker picks up and runs listeners in background |
| `False` | `True` | Rarely useful — publishes to Redis but still blocks on local listener completion |

### event_id and serialisation

Every `Event` instance automatically receives a `self.event_id = str(uuid.uuid4())`. This ID is preserved across Redis serialisation so all workers see the same ID — which is what `ttl`-based deduplication locks on.

`to_dict()` is called when publishing to Redis. The default implementation serialises all public instance attributes. Override it for non-JSON-serialisable fields:

```python
class OrderCreated(Event):
    redis = True

    def __init__(self, order_id: int, items: list) -> None:
        self.order_id = order_id
        self.items = items          # list of ORM objects — not directly JSON-serialisable

    def to_dict(self) -> dict:
        base = super().to_dict()    # includes event_id + order_id automatically
        base["items"] = [{"id": i.id, "name": i.name} for i in self.items]
        return base

    @classmethod
    def from_dict(cls, data: dict) -> "OrderCreated":
        obj = cls.__new__(cls)
        obj.event_id  = data["event_id"]
        obj.order_id  = data["order_id"]
        obj.items     = data["items"]   # already plain dicts on the receiving side
        return obj
```

The default `from_dict` sets all keys from the dict as instance attributes, so override is only needed for custom reconstruction.

### @listen decorator

```python
# app/listeners/order_listener.py
from forgeapi import listen
from app.events.order_created_event import OrderCreated

@listen(OrderCreated)
async def send_confirmation(event: OrderCreated) -> None:
    await mailer.send(f"Order #{event.order_id} total: {event.total}")

@listen(OrderCreated)
async def update_inventory(event: OrderCreated) -> None:
    await Inventory.decrease(order_id=event.order_id)
```

Both listeners are registered at import time. `Core(app, events=True)` imports all files in `listeners_dir` automatically.

Multiple listeners for the same event run **in parallel** via `asyncio.gather`.

An alternative is `@bus.on` — identical registration, different import path:

```python
from forgeapi import EventBus

bus = EventBus.get_instance()

@bus.on(OrderCreated)
async def log_order(event: OrderCreated) -> None:
    logger.info("order %d created, total=%.2f", event.order_id, event.total)
```

### Dispatching

```python
@route.post("/orders")
async def create(self, payload: OrderCreatePayload, user: CurrentUser) -> OrderResponse:
    order = await Order.create(**payload.model_dump(), user_id=int(user.id))
    await OrderCreated(order_id=order.id, total=order.total).dispatch()
    return OrderResponse.model_validate(order)
```

`dispatch()` is an instance method — always call it on a freshly constructed event object. The same event object should not be dispatched twice.

### Background vs synchronous dispatch

`background = False` (default): the route handler waits for all listeners to finish before sending the response. Use when the response depends on the side effects, or when ordering matters.

`background = True`: listeners are scheduled as an `asyncio.Task` and the response is returned immediately. Use for fire-and-forget work like emails, analytics, cache warming.

```python
# background=False — response returned AFTER send_welcome_email and create_profile finish
class UserRegistered(Event):
    background = False

    def __init__(self, user_id: int, email: str) -> None:
        self.user_id = user_id
        self.email   = email

# background=True — response returned immediately, notifications sent after
class OrderShipped(Event):
    background = True

    def __init__(self, order_id: int) -> None:
        self.order_id = order_id
```

### Exception isolation

Each listener is wrapped in a try/except. If one listener raises, the exception is **logged** but does not propagate — other listeners still run and the route handler is not affected.

```python
@listen(OrderShipped)
async def send_sms(event: OrderShipped) -> None:
    raise RuntimeError("SMS gateway down")   # logged, does NOT kill the request

@listen(OrderShipped)
async def update_inventory(event: OrderShipped) -> None:
    await Inventory.ship(event.order_id)    # still runs
```

### EventBus

`Core(app, events=True)` calls `EventBus.load_from_dir("app/listeners")` which imports every `*.py` file in the listeners directory. `@listen` registers on import — no manual wiring needed.

```python
from forgeapi import EventBus

# singleton
bus = EventBus.get_instance()

# manual registration (without decorator)
bus.register(OrderCreated, my_async_handler)

# inspect registered listeners
listeners = bus.listeners_for(OrderCreated)  # → [send_confirmation, update_inventory]

# reset singleton and all registrations — useful in tests
EventBus.reset()
```

---

### Redis pub/sub — EventBus

The built-in `EventBus` supports Redis pub/sub for distributing events across multiple workers (replicas) of the **same project**. Add `redis = True` to any event class:

```python
# app/events/order_shipped_event.py
from forgeapi import Event

class OrderShipped(Event):
    background = True
    redis = True      # publish to Redis; all workers receive it
    ttl = 300         # dedup window — only the first worker that wins the lock processes it

    def __init__(self, order_id: int) -> None:
        self.order_id = order_id
```

Wire up Redis in the app lifespan:

```python
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
import redis.asyncio as aioredis
from forgeapi import Core, EventBus

@asynccontextmanager
async def lifespan(app: FastAPI):
    bus = EventBus.get_instance()
    await bus.redis_connect("redis://localhost:6379")   # no redis.asyncio import needed
    task = asyncio.create_task(bus.start_redis_subscriber())
    yield
    task.cancel()
    await bus.redis_disconnect()

app = FastAPI(lifespan=lifespan)
Core(app, events=True)
```

Dispatching is unchanged — `await OrderShipped(order_id=42).dispatch()`.

**How dedup works:** when `ttl` is set, the subscriber performs `SET NX EX {ttl} forgeapi:dedup:{event_id}` before running listeners. Only the first worker that acquires the key processes the event; all others skip it silently.

| `redis` | `ttl` | Behaviour |
|---|---|---|
| `False` (default) | — | Local dispatch only, no Redis |
| `True` | `None` | Published to Redis, **all** subscribers run listeners |
| `True` | `60` | Published to Redis, exactly one subscriber processes per 60-second window |

---

### Redis Streams — EventBus

Use `redis_type = "stream"` when you need **persistent delivery with consumer groups** — messages survive worker restarts and each independent group receives every message exactly once.

```python
# app/events/order_event.py
from forgeapi import Event

class OrderEvent(Event):
    background = True
    redis      = True
    redis_type = "stream"    # XADD instead of PUBLISH
    namespace  = "shop"      # stream key → shop:OrderEvent

    def __init__(self, order_id: int, total: float, customer: str) -> None:
        self.order_id = order_id
        self.total    = total
        self.customer = customer
```

Wire up the publisher (FastAPI):

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    bus = EventBus.get_instance()
    await bus.redis_connect("redis://localhost:6379")
    yield
    await bus.redis_disconnect()
```

Wire up each consumer (standalone bot / worker):

```python
import asyncio
from forgeapi import EventBus
from app.events.order_event import OrderEvent

async def main():
    bus = EventBus.get_instance()
    await bus.redis_connect("redis://localhost:6379")

    @bus.on(OrderEvent)
    async def on_order(event: OrderEvent):
        print(f"order_id={event.order_id}  customer={event.customer}")

    await bus.start_stream_subscriber(
        group="bot1",           # consumer group name — each group gets every message
        consumer="bot1-worker", # worker id within the group
        event_classes=[OrderEvent],
    )

asyncio.run(main())
```

Run two independent bots — both receive every order:

```
# Windows PowerShell
$env:BOT_NAME="bot1"; python bot.py
$env:BOT_NAME="bot2"; python bot.py
```

**Pub/Sub vs Streams**

| | `redis_type="pubsub"` | `redis_type="stream"` |
|---|---|---|
| Transport | `PUBLISH` / `SUBSCRIBE` | `XADD` / `XREADGROUP` |
| Persistence | None — lost if no subscriber | Stored until all groups ACK |
| Delivery | All subscribers simultaneously | Each group independently |
| Offline workers | Miss messages | Catch up on reconnect |
| Dedup | `ttl` class var + SET NX | Not built-in |
| Use case | Same-project multi-worker fan-out | Cross-service / bots that must not miss messages |

### Testing events

Always reset the bus before and after each test — listeners registered in one test bleed into the next otherwise.

```python
import pytest
from forgeapi import EventBus

@pytest.fixture(autouse=True)
def reset_bus():
    EventBus.reset()
    yield
    EventBus.reset()
```

For background events (`background=True`) use `asyncio.gather` to wait for all scheduled tasks before asserting:

```python
import asyncio
import pytest
from forgeapi import EventBus, listen
from app.events.order_shipped_event import OrderShipped

@pytest.mark.anyio
async def test_order_shipped_notifies_warehouse():
    results = []

    @listen(OrderShipped)
    async def capture(event: OrderShipped) -> None:
        results.append(event.order_id)

    bus = EventBus.get_instance()
    await OrderShipped(order_id=42).dispatch()

    # flush all background tasks
    await asyncio.gather(*bus._bg_tasks, return_exceptions=True)

    assert results == [42]
```

For synchronous events (`background=False`) the `await event.dispatch()` line already waits — no extra flush needed.

---

### RedisBus — cross-project bridge

`RedisBus` is a **standalone** Redis pub/sub bus for communication between **different projects** on the same server. It has no connection to the per-process `EventBus` singleton — both projects only share a Redis URL.

```python
from forgeapi import RedisBus
```

#### Setup — both projects

```python
# project_a/events.py  AND  project_b/events.py — same code, same Redis URL
bus = RedisBus("redis://localhost:6379", namespace="shop")
```

`namespace` is a channel prefix that isolates projects. Two projects with different namespaces never receive each other's events. Two projects with the **same** namespace share all events — which is exactly what cross-project communication needs.

#### Publishing

```python
# plain dict
await bus.emit("order:created", {"id": 42, "total": 99.9})

# Tortoise model — scalar fields are serialised automatically
order = await Order.get(id=42)
await bus.emit("order:created", order)

# prefetch relations to include them in the payload
order = await Order.get(id=42).prefetch_related("items")
await bus.emit("order:created", order)
```

`datetime`, `Decimal`, and `UUID` are converted to JSON automatically.  
Un-fetched FK relations are skipped; only the `_id` column is included.

#### Subscribing

```python
@bus.on("order:created")
async def handle_order(data: dict) -> None:
    await telegram.send(f"New order #{data['id']}, total: {data['total']}")
    # reply back to Project A
    await bus.emit("notification:sent", {"order_id": data["id"]})
```

Multiple handlers on the same channel all run in parallel. Handlers receive a plain `dict` — no shared Python classes needed between projects.

#### Lifecycle — FastAPI

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from forgeapi import RedisBus

bus = RedisBus("redis://localhost:6379", namespace="shop")

@bus.on("order:created")
async def handle_order(data: dict) -> None:
    await telegram.send(f"Order #{data['id']}")
    await bus.emit("notification:sent", {"order_id": data["id"]})

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with bus:   # connects + starts listener coroutine in existing event loop
        yield         # disconnects + cancels listener on shutdown

app = FastAPI(lifespan=lifespan)
```

#### Lifecycle — standalone script (no FastAPI)

```python
import asyncio
from forgeapi import RedisBus

bus = RedisBus("redis://localhost:6379", namespace="shop")

@bus.on("order:created")
async def handle(data: dict) -> None:
    print("received:", data)

async def main():
    async with bus:
        await asyncio.sleep(float("inf"))

asyncio.run(main())
```

#### Manual control

```python
await bus.connect()
task = asyncio.create_task(bus.listen())  # safe in existing event loop

# later
task.cancel()
await bus.disconnect()
```

#### Full cross-project example

```
Project A (shop)                Redis (namespace="shop")       Project B (notifier)
────────────────                ───────────────────────        ────────────────────
order = await Order.get(42)              │                     @bus.on("order:created")
await bus.emit(                          │                     async def handle(data):
  "order:created", order     ──publish──►│◄──subscribe──         await tg.send(...)
)                                        │                       await bus.emit(
                                         │                         "notification:sent",
@bus.on("notification:sent") ◄──subscribe│──publish──►             {"order_id": data["id"]}
async def handle(data):                  │                       )
  await Order.filter(                    │
    id=data["order_id"]                  │
  ).update(notified=True)               │
```

#### `RedisBus` vs `EventBus`

| | `EventBus` | `RedisBus` |
|---|---|---|
| Scope | Same project, multiple workers | Different projects |
| Channel key | Python class | String name |
| Payload | Typed `Event` instance | Plain `dict` |
| Shared code needed | Yes — event classes | No |
| Transport | Optional Redis via `set_redis()` | Always Redis |
| Dedup | `ttl` on event class | Not built-in |

---

## 8. Controllers

Controllers are classes that group routes. `Core` auto-discovers all `*_controller.py` files in `controllers_dir` (recursively) and registers their routers under `base_prefix`.

### Base pattern

```python
# app/controllers/post_controller.py
from forgeapi.controllers import Controller, route
from forgeapi.auth import CurrentUser
from forgeapi.pagination import Pagination
from app.models import Post
from app.schemas.response.post import PostResponse
from app.schemas.payload.post import PostCreatePayload, PostUpdatePayload

class PostController(Controller):
    prefix = "/posts"
    tags   = ["posts"]

    @route.get("/")
    async def index(self, pagination: Pagination) -> dict:
        total = await Post.all().count()
        items = await Post.all().offset(pagination.offset).limit(pagination.limit)
        return {"items": [PostResponse.model_validate(p) for p in items], "total": total}

    @route.post("/", response_model=PostResponse, status_code=201)
    async def create(self, payload: PostCreatePayload, user: CurrentUser) -> PostResponse:
        post = await Post.create(**payload.model_dump(), author_id=int(user.id))
        return PostResponse.model_validate(post)

    @route.get("/{post_id}", response_model=PostResponse)
    async def show(self, post_id: int) -> PostResponse:
        post = await Post.get_or_none(id=post_id)
        if not post:
            raise HTTPException(404, "Not found")
        return PostResponse.model_validate(post)

    @route.patch("/{post_id}", response_model=PostResponse)
    async def update(self, post_id: int, payload: PostUpdatePayload, user: CurrentUser) -> PostResponse:
        post = await Post.get_or_none(id=post_id, author_id=int(user.id))
        if not post:
            raise HTTPException(404, "Not found or not yours")
        for field, value in payload.model_dump(exclude_none=True).items():
            setattr(post, field, value)
        await post.save()
        return PostResponse.model_validate(post)

    @route.delete("/{post_id}")
    async def destroy(self, post_id: int, user: CurrentUser) -> dict:
        post = await Post.get_or_none(id=post_id, author_id=int(user.id))
        if not post:
            raise HTTPException(404, "Not found or not yours")
        await post.delete()
        return {"detail": "deleted"}
```

### Route decorator

```python
from forgeapi.controllers import Controller, route

# shorthand — preferred
@route.get("/")
@route.post("/")
@route.put("/{id}")
@route.patch("/{id}")
@route.delete("/{id}")

# explicit form — still works, supports multiple methods
@route("/", methods=["GET"])
@route("/{id}", methods=["PATCH", "PUT"])
```

All kwargs are forwarded to FastAPI:

```python
@route.post("/", response_model=PostResponse, status_code=201, summary="Create post",
            dependencies=[Depends(some_dep)])
async def create(self, payload: PostCreatePayload) -> PostResponse: ...
```

### Auto-prefix and namespace

If `prefix` is not set on the class, it is derived from the class name at definition time.

**Formula** (strip `Controller`, split on CamelCase):

```
/{first-word}/{remaining-words-joined-with-hyphens-then-pluralised}
```

The result is **always exactly two path segments** — one slash, never more. Hyphens appear only inside the resource part when there are two or more remaining words.

| Class → split | Namespace | Resource | Auto prefix |
|---|---|---|---|
| `UserController` → `[User]` | — | `users` | `/users` |
| `AdminUserController` → `[Admin, User]` | `admin` | `users` | `/admin/users` |
| `SuperAdminReportController` → `[Super, Admin, Report]` | `super` | `admin-reports` | `/super/admin-reports` |
| `SuperAdminOrderItemController` → `[Super, Admin, Order, Item]` | `super` | `admin-order-items` | `/super/admin-order-items` |

The slash in `/admin/users` is the **namespace/resource separator** — not a word separator. The same slash appears in `/super/admin-reports`. There is always exactly one.

### API versioning — use base_prefix, not the controller name

`Core` prepends `base_prefix` (default `/api/v1`) to every controller's prefix automatically. **Do not encode the API version in the controller name.** A `PostController` with auto-prefix `/posts` is registered as `/api/v1/posts` — no naming change needed.

```toml
# forgeapi.toml
[structure]
base_prefix = "/api/v1"
```

```python
Core(app)                          # uses base_prefix from toml → /api/v1/posts
Core(app, base_prefix="/api/v2")   # override inline
```

Final URL = `base_prefix` + `controller.prefix` + `route path`

### make:controller file placement

The CLI uses its own rule for where to write the file: **all CamelCase words except the last** form the subdirectory path; the **last word** is the resource. It writes `prefix` explicitly into the generated file, so auto-derivation is irrelevant for generated controllers.

```bash
forgeapi make:controller Post          # controllers/post_controller.py
                                        # prefix = "/posts"
forgeapi make:controller AdminUser     # controllers/admin/user_controller.py
                                        # prefix = "/admin/users"
forgeapi make:controller SuperAdminOrder  # controllers/super/admin/order_controller.py
                                           # prefix = "/super/admin/orders"
```

```
controllers/
  post_controller.py          # PostController        → /api/v1/posts
  admin/
    __init__.py
    user_controller.py        # AdminUserController   → /api/v1/admin/users
  super/
    __init__.py
    admin/
      __init__.py
      order_controller.py     # SuperAdminOrderController → /api/v1/super/admin/orders
```

`Core` discovers all of these automatically via recursive glob.

---

## 9. Schemas

### Base classes

```python
from forgeapi import BaseSchema, BaseCreateSchema, BaseUpdateSchema
```

**`BaseSchema`** — response schemas. Adds `id: int | str` (supports both integer and UUID primary keys), `created_at: datetime`, `updated_at: datetime`. Has `from_attributes=True` so it reads directly from Tortoise model instances.

```python
class PostResponse(BaseSchema):
    title: str
    body:  str

return PostResponse.model_validate(post)
```

**`BaseCreateSchema`** — POST payloads. Plain `BaseModel` subclass.

```python
class PostCreatePayload(BaseCreateSchema):
    title: str
    body:  str
    is_published: bool = True
```

**`BaseUpdateSchema`** — PATCH payloads. Plain `BaseModel` subclass. **Enforces that every field is `Optional`** — declaring a field without a default value (i.e. required) raises `TypeError` at class definition time, not at runtime:

```python
class PostUpdatePayload(BaseUpdateSchema):
    title: str | None = None   # OK
    body:  str | None = None   # OK
    # title: str               # TypeError at class definition time

# applying a partial update:
for field, value in payload.model_dump(exclude_none=True).items():
    setattr(post, field, value)
await post.save()
```

### Schema directories

Recommended layout:

```
schemas/
  payload/
    __init__.py
    post.py       # PostCreatePayload, PostGetPayload, PostUpdatePayload
    user.py       # UserCreatePayload, UserGetPayload, UserUpdatePayload
  response/
    __init__.py
    post.py       # PostResponse, PostListResponse
    user.py       # UserResponse, UserListResponse
```

### generate:schema

Generate typed schemas from an existing Tortoise model by reading `_meta.fields_map` at runtime.

```bash
forgeapi generate:schema Post --payload             # cru by default
forgeapi generate:schema Post --response            # Response + ListResponse
forgeapi generate:schema Post --payload --response  # both
forgeapi generate:schema Post --payload -crud       # all four payload classes
forgeapi generate:schema Post --payload --cu        # Create + Update only
```

**`--payload`** output:

| CRUD flag | Class | Base |
|---|---|---|
| `c` | `PostCreatePayload` | `BaseCreateSchema` |
| `r` | `PostGetPayload` | `BaseModel` (all Optional, for filtering) |
| `u` | `PostUpdatePayload` | `BaseUpdateSchema` |
| `d` | `PostDeletePayload` | `BaseModel` |

Default when `--payload` is given without CRUD flags: `cru` (no delete).  
Use `-d` or `-crud` to include delete.

**`--response`** always generates exactly:

```python
class PostResponse(BaseSchema):
    title: str        # real types from the model
    body:  str
    ...

class PostListResponse(BaseModel):
    items: list[PostResponse]
    total: int
```

If the model isn't found, `pass` stubs are generated — the command still succeeds.

---

## 10. Permissions

Spatie-style roles and permissions using **polymorphic pivot tables**. Any number of models can have roles and permissions without creating extra junction tables per model.

### How it works

Instead of `user_roles` / `user_permissions` per model, two shared tables store all assignments:

```
model_has_roles        model_has_permissions
──────────────────     ──────────────────────
model_type  = "user"   model_type  = "user"
model_id    = 42       model_id    = 42
role_id     = 1        permission_id = 3
```

`model_type` is the lowercase class name. Adding permissions to a new model (e.g. `Team`) requires zero new migrations — it reuses the same two tables.

> The permission models register under the `models` app — no separate `permissions` app needed in your config.

### DB tables

| Table | Description |
|---|---|
| `permissions` | Permission records (`id`, `name`, `guard`) |
| `roles` | Role records (`id`, `name`, `guard`) |
| `role_permissions` | Role ↔ Permission M2M |
| `model_has_roles` | Polymorphic — `model_type`, `model_id`, `role_id` |
| `model_has_permissions` | Polymorphic — `model_type`, `model_id`, `permission_id` |

---

### Setup

**1. Add `PermissionsMixin` to your model:**

```python
# database/models/user.py
from tortoise import fields
from forgeapi.permissions import PermissionsMixin

class User(PermissionsMixin):
    id       = fields.IntField(pk=True)
    username = fields.CharField(max_length=150, unique=True)
    email    = fields.CharField(max_length=255, unique=True)

    class Meta:
        table = "users"
```

`PermissionsMixin` is `abstract = True` — it adds no columns and no junction tables to `users`. All assignments are stored in the shared polymorphic pivots.

**2. Add permissions models to your Tortoise config:**

```python
# app/config.py
TORTOISE_ORM = {
    "apps": {
        "models": {
            "models": ["database.models", "forgeapi.permissions.models"],  # ← add here
            "default_connection": "default",
            "migrations": "database.migrations",
        },
    },
    ...
}
```

**3. Register in `Core`:**

```python
# Auto-detect — Core scans models_dir and finds the PermissionsMixin subclass
core = Core(app, auth=True, permissions=True)

# Explicit — required when you have multiple PermissionsMixin models
from database.models import User
core = Core(app, auth=True, permissions=User)
```

**4. Run migrations:**

```bash
forgeapi db:makemigrations && forgeapi db:migrate
```

---

### PermissionsMixin — all methods

All methods are `async`.

#### Checking permissions

All check methods accept an optional `guard` keyword argument (default `"api"`) that scopes the lookup to a specific auth guard, preventing cross-guard permission leakage.

```python
await user.can("edit:posts")                         # True if has ANY of the given perms (direct or via role)
await user.can("edit:posts", "admin")                # True if has ANY one of the two
await user.can("edit:posts", guard="web")            # check against a specific guard
await user.cannot("delete:users")                    # inverse of can()
await user.has_all_permissions("read", "write")      # True only if has ALL

await user.get_all_permissions()                     # → ["edit:posts", "admin", ...]
await user.get_all_permissions(guard="web")          # scoped to a guard
```

#### Granting / revoking permissions

```python
await user.give_permission("edit:posts", "delete:posts")
await user.revoke_permission("delete:posts", "edit:posts")   # one or many
```

#### Checking roles

```python
await user.has_role("admin")                  # True if has ANY of the given roles
await user.has_role("admin", "editor")        # True if has ANY one
await user.has_all_roles("admin", "editor")   # True only if has ALL

await user.get_role_names()   # → ["admin", "editor"]
```

#### Assigning / removing roles

```python
await user.assign_role("admin", "editor")
await user.remove_role("editor", "viewer")   # one or many
```

#### Filtering collections by role

Class-level methods — return a Tortoise `QuerySet` that you can chain freely.

```python
# all non-admins
users = await (await User.without_role("admin"))

# all admins
users = await (await User.with_role("admin"))

# chain additional filters
qs = await User.without_role("admin")
users = await qs.filter(is_active=True).order_by("id").all()

# count
count = await User.without_role("admin").count()  # still async
```

`with_role` / `without_role` accept multiple role names — any match is sufficient:

```python
# users that are neither admin nor moderator
users = await (await User.without_role("admin", "moderator"))
```

---

### Dependencies

Enforce access control in route handlers. Both return the DB user instance on success, raise `401` for an invalid/inactive user, or raise `403` (with a generic `"Forbidden"` detail — no internal permission names are exposed) when the check fails.

```python
from forgeapi.permissions import require_permission, require_role

# Aliases kept for backward compatibility
from forgeapi.permissions import RequirePermission, RequireRole
```

**`require_permission(*permissions)`** — user must have **at least one**:

```python
@route.delete("/{id}")
async def destroy(self, id: int, user=require_permission("delete:posts")):
    ...

@route.post("/")
async def create(self, payload: PostCreatePayload, user=require_permission("create:posts", "admin")):
    ...
```

**`require_role(*roles)`** — user must have **at least one**:

```python
@route.get("/admin/stats")
async def stats(self, user=require_role("admin")):
    ...

@route.get("/dashboard")
async def dashboard(self, user=require_role("admin", "moderator")):
    ...
```

Both dependencies also check `db_user.is_active` when the field exists on the model — inactive users receive `401` rather than proceeding to the permission check.

To resolve the user model per FastAPI app instance (useful in multi-app or multi-tenant setups) set `app.state.user_model = YourUserModel` in your lifespan; the dependencies prefer `request.app.state.user_model` and fall back to the global registry set by `Core`.

---

### Role model

`Role` itself can have permissions — useful for bulk assignment.

```python
from forgeapi.permissions.models import Role, Permission

role = await Role.find_or_create("editor")

await role.give_permission("edit:posts", "read:posts")
await role.revoke_permission("read:posts")
await role.has_permission("edit:posts")            # → bool
await role.has_permission("edit:posts", guard="web")  # scoped to guard

# assigning a role gives the user all permissions of that role
await user.assign_role("editor")
await user.can("edit:posts")   # → True (via role)
```

---

## 11. Middleware

Two extension points: **global middleware** wraps every request, **guards** are scoped to a route or controller via DI.

---

### Custom global middleware

Subclass `Middleware`, override `dispatch` — the standard Starlette hook. `call_next` passes the request to the handler and returns the response.

```python
from forgeapi import Middleware
from fastapi import Request, Response
from typing import Callable

class TimingMiddleware(Middleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        import time
        start = time.perf_counter()
        response = await call_next(request)
        response.headers["X-Process-Time"] = f"{time.perf_counter() - start:.3f}s"
        return response
```

**Register:**

```python
# at Core init
core = Core(app, middleware=[TimingMiddleware])

# multiple, with kwargs via tuple
core = Core(app, middleware=[
    TimingMiddleware,
    (TenantMiddleware, {"default_tenant": "acme"}),
])

# after init — chainable
core.use(TimingMiddleware)
core.use(TenantMiddleware, default_tenant="acme")
```

Use `request.state` to pass data to downstream handlers:

```python
class TenantMiddleware(Middleware):
    def __init__(self, app, default_tenant: str = "public"):
        super().__init__(app)
        self.default_tenant = default_tenant

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        request.state.tenant = request.headers.get("X-Tenant", self.default_tenant)
        return await call_next(request)
```

To short-circuit the request without reaching the handler:

```python
from fastapi.responses import JSONResponse

class MaintenanceMiddleware(Middleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if request.headers.get("X-Bypass") != "secret":
            return JSONResponse({"detail": "Under maintenance"}, status_code=503)
        return await call_next(request)
```

---

### Guards — per-route / per-controller

Guards are FastAPI dependencies. They run before the handler and raise `HTTPException` to block access. Unlike global middleware they can target a single route or a whole controller.

Subclass `Guard` and override `handle`. FastAPI injects parameters declared in `handle` automatically — the same way as a regular route handler. `__call__` is internal and mirrors `handle`'s signature at class creation time.

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

**Per-route:**

```python
from fastapi import Depends

class PostController(Controller):
    @route.post("/", dependencies=[Depends(ApiKeyGuard())])
    async def create(self, payload: PostCreatePayload): ...
```

**Per-controller** — `guards` applies to every route in the class:

```python
class AdminController(Controller):
    prefix = "/admin"
    guards = [ApiKeyGuard("X-Admin-Key")]

    @route.get("/stats")
    async def stats(self): ...

    @route.get("/users")
    async def users(self): ...
```

Declare FastAPI dependencies directly in `handle` — they are injected automatically:

```python
from forgeapi.auth import CurrentUser

class ActiveUserGuard(Guard):
    async def handle(self, user: CurrentUser) -> None:
        if not user.is_active:
            raise HTTPException(403, "Account disabled")

class AdminController(Controller):
    guards = [ActiveUserGuard()]
```

Mix `Guard` instances and raw `Depends` in `guards`:

```python
class AdminController(Controller):
    guards = [
        ActiveUserGuard(),           # auto-wrapped in Depends
        Depends(require_admin_role), # raw Depends — used as-is
    ]
```

---

### Built-in middleware

Configured via `Core` keyword arguments.

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
Core(app, rate_limit=200)    # 200 req/min
```

```json
{"success": false, "error": {"code": "RATE_LIMITED", "message": "Too many requests. Slow down."}}
```

#### Request ID

```python
Core(app, request_id=True)
```

Access in a route or downstream middleware via `request.state.request_id`.

#### Access logging

Logger name: `forgeapi.access`. Format: `GET /api/v1/users → 200 [12.3ms] req_id=abc`.

```python
Core(app, logging=False)  # disable

import logging
logging.getLogger("forgeapi.access").setLevel(logging.WARNING)
```

---

## 12. Settings

`BaseAppSettings` wraps `pydantic-settings` with `.env` file loading out of the box.

```python
from forgeapi.settings import BaseAppSettings

class Settings(BaseAppSettings):
    database_url: str
    redis_url: str | None = None
    jwt_secret: str
    debug: bool = False
    app_name: str = "My App"   # overrides the default

settings = Settings()   # reads .env automatically
```

`.env` file:

```bash
DATABASE_URL=postgresql://user:pass@localhost/mydb
JWT_SECRET=supersecret
DEBUG=true
```

`BaseAppSettings` already has `debug: bool = False` and `app_name: str = "FastAPI App"`.  
All env vars are case-insensitive. Unknown vars are ignored (`extra="ignore"`).

### Sensitive field masking

`BaseAppSettings.__repr__` automatically masks fields whose names contain any of: `password`, `secret`, `token`, `key`, `auth`, `credential`. Masked values are shown as `***` when the settings object is printed or logged:

```python
>>> print(settings)
Settings(database_url='postgresql://...', jwt_secret='***', debug=True)
```

This prevents accidental credential exposure in logs and error messages. The actual field value is unaffected — masking only applies to `__repr__`.

---

## 13. Seeders

Seeders populate the database with initial or test data. The `database/seeds/` directory is created automatically by `forgeapi init`.

### Creating a seeder

```bash
forgeapi make:seed User
# → database/seeds/user_seeder.py
```

Generated file:

```python
from forgeapi.database import Seeder

class UserSeeder(Seeder):
    async def run(self) -> None:
        pass
```

Implement `run()` using Tortoise ORM — it runs inside an active DB connection:

```python
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
```

### Running seeders

```bash
forgeapi db:seed              # run all *_seeder.py files in seeds_dir
forgeapi db:seed User         # run only UserSeeder
forgeapi db:seed User Post    # run specific seeders in order
```

Seeders are discovered by filename: `forgeapi db:seed User` looks for `database/seeds/user_seeder.py`.

### Transaction behaviour

The CLI (`db:seed`) calls `Seeder.execute()`, which wraps `run()` in an explicit database transaction:

```python
async with in_transaction():
    await seeder.run()
```

If `run()` raises any exception the transaction is rolled back and no partial data is committed. When you call `run()` directly (e.g. from a test or another seeder), **no transaction wrapper is added** — you are responsible for wrapping it yourself if atomicity matters:

```python
from tortoise.transactions import in_transaction

async with in_transaction():
    await UserSeeder().run()
```

### Seeder base class

```python
from forgeapi.database import Seeder
```

| Method | Description |
|---|---|
| `async run(self) -> None` | Override to define seed logic. Called once per seeder run. |

---

## 14. CLI reference

Add `-h` after any command for detailed help:

```bash
forgeapi make:controller -h
forgeapi generate:schema -h
forgeapi make -H           # list all make: variants
```

---

### `forgeapi init <project-name>`

Scaffold a new project.

```bash
forgeapi init my-blog
```

Asks for:
- Auth strategy: `jwt` / `cookie` / `telegram`
- DB driver: `asyncpg` / `aiosqlite` / `aiomysql`
- Welcome boilerplate: User + Post + events (y/n)

Creates the full project skeleton including `database/seeds/` for seeders.

---

### `forgeapi make:controller <Name> [flags]`

Generate a controller. CamelCase namespace supported — all words except the last become the subdirectory path; the last word is the resource.

```bash
forgeapi make:controller User                 # controllers/user_controller.py
forgeapi make:controller User --ms            # + model + stub schemas
forgeapi make:controller AdminUser            # controllers/admin/user_controller.py
forgeapi make:controller SuperAdminOrder      # controllers/super/admin/order_controller.py
```

API versioning comes from `base_prefix` in config, not the controller name — use `make:controller Post`, not `make:controller ApiV1Post`.

| Flag | Short | Generates |
|---|---|---|
| `--model` | `-m` | Tortoise model |
| `--schema` | `-s` | Stub schemas |

Compound: `--ms` `--mc` `--mcs` `-ms` `-cs` etc.

---

### `forgeapi make:model <Name> [flags]`

```bash
forgeapi make:model Post
forgeapi make:model Post -cs            # + controller + schema

# --alias: write into a specific file instead of the default <name>.py
# If the file already exists and is non-empty, the class is appended at the end
forgeapi make:model Employee --alias Worker     # → models/worker.py  (creates)
forgeapi make:model Contractor --alias Worker   # → models/worker.py  (appends)
```

| Flag | Short | Description |
|---|---|---|
| `--controller` | `-c` | Also generate controller |
| `--schema` | `-s` | Also generate stub schemas |
| `--alias <FileName>` | — | Target file name in models_dir (snake_case). Appends if file exists. |

---

### `forgeapi make:schema <Name> [flags]`

Generate stub schemas (3 classes with `pass`). For typed schemas from an existing model use `generate:schema`.

```bash
forgeapi make:schema Post
forgeapi make:schema Post --mc  # + model + controller
```

---

### `forgeapi make:event <Name>`

```bash
forgeapi make:event UserRegistered
# → app/events/user_registered_event.py
```

---

### `forgeapi make:listener <Name>`

```bash
forgeapi make:listener UserRegistered
# → app/listeners/user_registered_listener.py
```

---

### `forgeapi generate:schema <Name> --payload | --response [crud]`

Generate typed schemas from an existing Tortoise model. At least one of `--payload` / `--response` required.

```bash
forgeapi generate:schema User --payload             # CreatePayload + GetPayload + UpdatePayload
forgeapi generate:schema User --response            # UserResponse + UserListResponse
forgeapi generate:schema User --payload --response  # both
forgeapi generate:schema User --payload -crud       # all four incl. DeletePayload
forgeapi generate:schema User --payload --cu        # Create + Update only
```

CRUD flags (`--payload` only):

| Flag | Operations |
|---|---|
| `--crud` | c + r + u (default — no delete) |
| `-crud` | c + r + u + d (all four) |
| `--cu` / `-cu` | create + update |
| `--cr` / `-cr` | create + read |
| `-d` | delete only |

`--response` ignores CRUD flags — always generates `{Name}Response` + `{Name}ListResponse`.

---

### `forgeapi runserver [options]`

```bash
forgeapi runserver
forgeapi runserver --reload
forgeapi runserver --port 9000 --host 0.0.0.0 --reload
```

---

### `forgeapi routers`

Print every registered route across all controllers — no DB connection needed.

```bash
forgeapi routers
# METHOD  PATH                          HANDLER
# GET     /api/v1/users/                UserController.index
# POST    /api/v1/users/register        UserController.register
```

---

### `forgeapi models`

List all Tortoise model classes found in `models_dir` with their table names and fields.

```bash
forgeapi models
```

---

### `forgeapi make:seed <Name>`

```bash
forgeapi make:seed User
# → database/seeds/user_seeder.py
```

---

### `forgeapi db:<subcommand>`

```bash
forgeapi db:init
forgeapi db:makemigrations
forgeapi db:makemigrations -n add_email_field
forgeapi db:migrate
forgeapi db:downgrade
forgeapi db:history
forgeapi db:seed              # run all seeders
forgeapi db:seed User Post    # run specific seeders
forgeapi db:fresh             # TRUNCATE all tables — clears data, keeps structure (asks confirmation)
forgeapi db:fresh --force     # DROP all tables including structure (asks confirmation, irreversible)
```

---

## 15. forgeapi.toml reference

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
strategy             = "jwt"        # jwt | cookie | telegram
jwt_secret_env       = "JWT_SECRET" # name of env var holding the secret
access_ttl_minutes   = 30
refresh_ttl_days     = 7

# cookie-only:
cookie_name          = "session"
cookie_httponly      = true
cookie_secure        = false        # set true in production (HTTPS)

[pagination]
default_limit = 20
max_limit     = 100
```

All fields are optional — `Core` works without a config file using the defaults above.

---

## 16. Telescope

Telescope is a built-in, in-process request debugger. It captures every HTTP request — including its SQL queries, log output, dispatched events, and custom job records — and streams the data to any connected WebSocket client in real time.

Telescope activates automatically when `debug=True` is passed to `Core`. It adds zero overhead to production builds.

```python
core = Core(app, debug=True)
```

> **Never use `debug=True` in production.** It exposes internal request data over an unauthenticated WebSocket endpoint.

### What Telescope captures

Each request is stored as a `RequestEntry` with the following fields:

| Field | Description |
|---|---|
| `method`, `path`, `query_string` | HTTP basics |
| `headers` | All request headers — sensitive headers replaced with `"***"` |
| `payload` | Parsed request body — sensitive fields recursively masked |
| `status` | Response HTTP status code |
| `response_body` | Parsed response body — same masking, capped at 64 KB |
| `duration_ms` | Total handler time in milliseconds |
| `timestamp` | ISO 8601 UTC timestamp |
| `queries` | List of SQL queries (text, params, duration, source location) |
| `logs` | All `logging` calls made during the request (level, logger, message, time) |
| `events` | Events dispatched during the request (class name, listener names, background flag) |
| `jobs` | Custom job executions recorded via `record_job()` |

Up to **200** entries are kept in a circular in-memory buffer. Oldest entries are evicted automatically when the buffer is full.

### WebSocket live stream

Connect to `ws://<host>/_forge/telescope/ws`. The protocol is:

| Direction | Message | Description |
|---|---|---|
| Server → Client | `{"type": "init", "data": [...]}` | Sent immediately on connect — all current entries |
| Server → Client | `{"type": "entry", "data": {...}}` | Sent after every completed HTTP request |
| Server → Client | `{"type": "clear"}` | Sent after the store is cleared |
| Client → Server | `{"type": "clear"}` | Clears all stored entries and broadcasts `{"type": "clear"}` to all clients |

Maximum 100 simultaneous WebSocket connections are accepted. The 101st connection is closed with code `1008`.

### Sensitive data masking

Telescope never stores plaintext credentials. Masking is applied in two layers:

**Headers** — the following header names are always replaced with `"***"`:
- `Authorization`
- `Cookie`
- `X-API-Key`
- `X-Telegram-Init-Data`

**Body fields** — any JSON key whose name contains one of these words is replaced with `"***"` (case-insensitive, recursive through nested objects and arrays):

```
password  secret  token  key  auth  credential  access_token  refresh_token
```

Example — a login request body `{"email": "user@example.com", "password": "s3cr3t"}` is stored as:

```json
{"email": "user@example.com", "password": "***"}
```

### SQL query tracking

When Tortoise ORM is installed, Telescope patches every `execute_*` method on every backend client at startup. Each query is recorded with:

| Field | Description |
|---|---|
| `sql` | The raw SQL string |
| `params` | Bound parameters |
| `duration_ms` | Query execution time |
| `location` | `file.py:line in function_name` — first non-framework frame in the call stack |

Failed queries (those that raise an exception) are also recorded — the `try/finally` wrapper ensures the record is appended even if the query errors.

### Log capture

A custom `logging.Handler` is added to the root logger. Every log record emitted during a request is appended to that request's `logs` list. Telescope's own logger (`forgeapi.telescope`) and the access logger (`forgeapi.access`) are excluded to prevent recursion — and so are all their sub-loggers.

### Event tracking

The `EventBus.dispatch` method is patched at startup. Whenever an event is dispatched during a request, Telescope records the event class name, the names of all registered listeners, and whether the event is background or not.

```json
{
  "event": "OrderCreated",
  "listeners": ["send_confirmation", "update_inventory"],
  "background": true
}
```

### Recording jobs

If you have a custom background job system, attach execution records to the current Telescope entry with `record_job()`:

```python
from forgeapi.telescope import record_job
import time

async def process_payment(order_id: int) -> None:
    t = time.perf_counter()
    try:
        await stripe.charge(order_id)
        record_job(
            "ProcessPayment",
            status="done",
            attempts=1,
            duration_ms=round((time.perf_counter() - t) * 1000, 3),
        )
    except Exception as exc:
        record_job(
            "ProcessPayment",
            status="failed",
            attempts=1,
            error=str(exc),
        )
        raise
```

`record_job()` is a no-op when called outside an active Telescope request context (e.g., from a background task or CLI command) — no error is raised.

```python
record_job(
    job: str,           # job class name or identifier
    status: str,        # "queued" | "running" | "done" | "failed"
    attempts: int = 1,
    duration_ms: float | None = None,
    error: str | None = None,
)
```

### Skipped paths

The following paths are never captured to prevent recording Telescope's own traffic or OpenAPI docs:

- `/_forge/telescope/...`
- `/docs`
- `/redoc`
- `/openapi.json`

### Performance notes

- `_caller_location()` in the SQL hook uses `sys._getframe()` instead of `traceback.extract_stack()` — no `FrameSummary` objects are allocated per query.
- Response body buffering is capped at **64 KB**. Larger responses are captured partially.
- Request body passed to `json.loads` is also capped at 64 KB.
- The WebSocket broadcast is scheduled as an `asyncio.Task` and never blocks the request path.

---

## 17. MCP Server

forge-kits ships an MCP server that exposes API docs and code generation tools directly to AI assistants (Claude Code, Cursor, etc.).

### Install

```bash
pip install forge-kits[mcp]
```

### Wire up in your project

Add to `.claude/settings.json` (or your editor's MCP config):

```json
{
  "mcpServers": {
    "forge-kits": {
      "command": "forgeapi-mcp"
    }
  }
}
```

### Available tools

| Tool | Description |
|---|---|
| `get_docs(topic)` | API reference for: `core`, `controllers`, `events`, `auth`, `permissions`, `pagination`, `schemas`, `middleware`, `cli`, `config` |
| `get_example(pattern)` | Complete working code for: `crud_controller`, `redis_event`, `stream_event`, `jwt_auth`, `rbac`, `pagination`, `guard` |
| `generate_controller(name, routes)` | Generate a `Controller` class |
| `generate_event(name, fields)` | Generate an `Event` class + listener |
| `generate_schema(name, fields, mode)` | Generate Pydantic schemas |
| `project_info(path)` | Read `forgeapi.toml` and scan project structure |
