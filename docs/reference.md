# ForgeAPI — Reference

- [Core](#core)
- [Configuration — forgeapi.toml](#configuration--forgeapitoml)
- [Auth](#auth)
  - [AuthBackend](#authbackend)
  - [CurrentUser / OptionalUser](#currentuser--optionaluser)
  - [JWTStrategy](#jwtstrategy)
  - [CookieStrategy](#cookiestrategy)
  - [TelegramStrategy](#telegramstrategy)
  - [AuthUser](#authuser)
- [Events](#events)
  - [Event](#event)
  - [EventBus](#eventbus)
  - [@listen](#listen)
  - [@bus.on](#buson)
- [RedisBus](#redisbus)
- [Controllers](#controllers)
  - [Controller](#controller)
  - [route](#route)
- [Middleware](#middleware)
  - [Middleware](#middleware-1)
  - [Guard](#guard)
- [Permissions](#permissions)
  - [PermissionsMixin](#permissionsmixin)
  - [Permission](#permission)
  - [Role](#role)
  - [require_permission / RequirePermission](#require_permission--requirepermission)
  - [require_role / RequireRole](#require_role--requirerole)
- [Schemas](#schemas)
- [Settings](#settings)
- [Pagination](#pagination)
- [Seeder](#seeder)
- [Telescope](#telescope)
  - [setup_telescope](#setup_telescope)
  - [record_job](#record_job)
  - [DebugStore](#debugstore)
  - [RequestEntry](#requestentry)
  - [ConnectionManager](#connectionmanager)
  - [DebugMiddleware](#debugmiddleware)
  - [Hooks](#hooks)

---

## Core

```python
from forgeapi import Core
```

Main entry point. Configures a FastAPI application with forgeapi modules.

```python
Core(
    app,
    *,
    auth: bool | str = False,
    cors: bool | list[str] = False,
    rate_limit: bool | int = False,
    pagination: bool | int = False,
    request_id: bool = False,
    events: bool = False,
    logging: bool = True,
    controllers: bool = True,
    permissions: bool | type | None = None,
    middleware: list | None = None,
    debug: bool = False,
    config_path: str = "forgeapi.toml",
)
```

### Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `app` | `FastAPI` | — | The FastAPI application to configure |
| `auth` | `bool \| str` | `False` | `True` uses strategy from `forgeapi.toml`; `"jwt"` / `"cookie"` / `"telegram"` overrides it |
| `cors` | `bool \| list[str]` | `False` | `True` allows all origins; pass a list for specific origins |
| `rate_limit` | `bool \| int` | `False` | `True` = 60 req/min; pass an int for a custom limit |
| `pagination` | `bool \| int` | `False` | `True` uses defaults from `forgeapi.toml`; int sets `default_limit` |
| `request_id` | `bool` | `False` | Injects `X-Request-ID` header into every response |
| `events` | `bool` | `False` | Auto-loads listener files from `listeners_dir` |
| `logging` | `bool` | `True` | Logs method, path, status, and duration for every request |
| `controllers` | `bool` | `True` | Auto-imports `*_controller.py` files and registers their routers |
| `permissions` | `bool \| type \| None` | `None` | `True` auto-detects a model; pass the class explicitly: `permissions=User` |
| `middleware` | `list \| None` | `None` | List of middleware classes (or `(cls, kwargs)` tuples) to register globally |
| `debug` | `bool` | `False` | Enables Telescope debug panel at `/_forge/telescope/requests` |
| `config_path` | `str` | `"forgeapi.toml"` | Path to the TOML config file |

### Methods

#### `core.use(middleware_cls, **kwargs) -> Core`

Register a custom middleware after `Core` is created. Returns `self` for chaining.

```python
core.use(TimingMiddleware)
core.use(TenantMiddleware, default_tenant="acme")
```

#### `core.include_router(router, prefix="", **kwargs) -> Core`

Include a FastAPI router, prepending the configured `base_prefix`.

```python
core.include_router(my_router, prefix="/internal")
```

#### `core.auth`

Property. Returns the configured `AuthBackend` instance, or `None` if auth was not enabled.

#### `core.config`

Property. Returns the loaded `KitConfig` instance.

### Example

```python
from fastapi import FastAPI
from forgeapi import Core

app = FastAPI()

core = Core(
    app,
    auth="jwt",
    cors=["https://example.com"],
    rate_limit=100,
    pagination=20,
    request_id=True,
    events=True,
    permissions=True,
)
```

---

## Configuration — forgeapi.toml

`forgeapi.toml` is optional. All values have defaults. Place it in the project root.

```toml
[project]
name        = "my-app"
version     = "0.1.0"
description = ""

[structure]
models_dir      = "database/models"
controllers_dir = "app/controllers"
schemas_dir     = "app/schemas"
events_dir      = "app/events"
listeners_dir   = "app/listeners"
seeds_dir       = "database/seeds"
base_prefix     = "/api/v1"

[auth]
strategy            = "jwt"         # jwt | cookie | telegram
jwt_secret_env      = "JWT_SECRET"
access_ttl_minutes  = 30
refresh_ttl_days    = 7
cookie_name         = "session"
cookie_httponly     = true
cookie_secure       = false

[pagination]
default_limit = 20
max_limit     = 100

[database]
tortoise_orm = "app.config.TORTOISE_ORM"
```

---

## Auth

### AuthBackend

```python
from forgeapi.auth import AuthBackend
```

Unified authentication interface that wraps any `AuthStrategy`.

```python
AuthBackend(strategy: AuthStrategy)
```

#### Methods

##### `auth.current_user() -> type`

Returns an `Annotated` type alias for a **required** authenticated user. Raises HTTP 401 if the request is unauthenticated.

```python
auth = AuthBackend(strategy=JWTStrategy(secret_key="s3cr3t"))
CurrentUser = auth.current_user()

@app.get("/me")
async def me(user: CurrentUser):
    return {"id": user.id}
```

##### `auth.optional_user() -> type`

Returns an `Annotated` type alias for an **optional** authenticated user. Returns `None` instead of raising 401.

```python
OptionalUser = auth.optional_user()

@app.get("/feed")
async def feed(user: OptionalUser):
    if user:
        return personalised_feed(user.id)
    return public_feed()
```

##### `auth.strategy`

Property. Returns the underlying `AuthStrategy` instance.

---

### CurrentUser / OptionalUser

```python
from forgeapi import CurrentUser, OptionalUser
# or
from forgeapi.auth import CurrentUser, OptionalUser
```

Global type aliases. Work when `Core(app, auth=True)` has been called. Use as type annotations — FastAPI resolves them as dependencies automatically.

```python
from forgeapi import CurrentUser, OptionalUser

@router.get("/profile")
async def profile(user: CurrentUser):        # 401 if not authenticated
    return user

@router.get("/home")
async def home(user: OptionalUser):          # None if not authenticated
    return {"personalised": user is not None}
```

---

### AuthUser

The Pydantic model returned by all auth strategies.

| Field | Type | Description |
|---|---|---|
| `id` | `Any` | User identifier from the token / session (`sub` claim) |
| `username` | `str \| None` | Username, if present in the token |
| `extra` | `dict` | Any additional claims from the token |
| `auth_method` | `str` | `"jwt"`, `"cookie"`, or `"telegram"` |

```python
@router.get("/me")
async def me(user: CurrentUser):
    print(user.id)           # "42"
    print(user.username)     # "alice"
    print(user.auth_method)  # "jwt"
    print(user.extra)        # {"role": "admin"}
```

---

### JWTStrategy

```python
from forgeapi import JWTStrategy
```

Bearer-token authentication. Reads `Authorization: Bearer <token>`.

```python
JWTStrategy(
    secret_key: str | None = None,       # falls back to JWT_SECRET env var
    algorithm: str = "HS256",
    access_token_expire_minutes: int = 30,
    refresh_token_expire_days: int = 7,
)
```

#### Methods

##### `strategy.create_access_token(payload: dict) -> str`

Creates a signed access token. Add `"sub"` (user id) and any extra claims. `"exp"` and `"type"` are set automatically.

```python
token = strategy.create_access_token({"sub": "42", "username": "alice", "role": "admin"})
```

##### `strategy.create_refresh_token(payload: dict) -> str`

Creates a signed refresh token with a longer expiry (`type: "refresh"`).

```python
refresh = strategy.create_refresh_token({"sub": "42"})
```

##### `strategy.decode(token: str) -> dict`

Decodes and verifies a JWT. Raises HTTP 401 if expired or invalid.

```python
payload = strategy.decode(token)
user_id = payload["sub"]
```

##### `strategy.blacklist(token: str) -> None`

No-op by default. Override for Redis-backed token revocation.

#### Full login example

```python
@router.post("/login")
async def login(data: LoginSchema):
    user = await User.get_or_none(email=data.email)
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(400, "Invalid credentials")

    strategy = core.auth.strategy  # JWTStrategy instance
    access  = strategy.create_access_token({"sub": str(user.id), "username": user.username})
    refresh = strategy.create_refresh_token({"sub": str(user.id)})
    return {"access_token": access, "refresh_token": refresh}
```

---

### CookieStrategy

```python
from forgeapi import CookieStrategy
```

HttpOnly session-cookie authentication. Stores a signed JSON payload.

```python
CookieStrategy(
    secret_key: str | None = None,   # falls back to COOKIE_SECRET env var
    cookie_name: str = "session",
    max_age: int = 3600,             # seconds
    httponly: bool = True,
    secure: bool = False,
    samesite: str = "lax",           # "lax" | "strict" | "none"
)
```

#### Methods

##### `strategy.set_cookie(response: Response, data: dict) -> None`

Signs `data` and writes it as a cookie on the response.

```python
@router.post("/login")
async def login(data: LoginSchema, response: Response):
    user = await authenticate(data)
    strategy.set_cookie(response, {"sub": str(user.id), "username": user.username})
    return {"ok": True}
```

##### `strategy.delete_cookie(response: Response) -> None`

Removes the session cookie.

```python
@router.post("/logout")
async def logout(response: Response):
    strategy.delete_cookie(response)
    return {"ok": True}
```

##### `strategy.create_session(data: dict) -> str`

Returns the raw signed cookie value without setting it. Useful when you manage the response manually.

---

### TelegramStrategy

```python
from forgeapi import TelegramStrategy
```

Validates Telegram Mini App `initData`. Accepts from:
- `X-Telegram-Init-Data` header
- `Authorization: tma <init_data>` header

```python
TelegramStrategy(
    bot_token: str | list[str],      # single token or list for multi-bot
    max_age_seconds: int = 86400,    # None disables expiry check
    debug: bool = False,             # skips auth_date check in development
)
```

#### Methods

##### `strategy.validate_init_data(init_data: str) -> TelegramUser`

Parses and validates raw `initData` string. Raises HTTP 401 on failure.

```python
tg_user = strategy.validate_init_data(raw_init_data)
print(tg_user.id, tg_user.username, tg_user.first_name)
```

#### `TelegramUser` fields

| Field | Type | Description |
|---|---|---|
| `id` | `int` | Telegram user ID |
| `username` | `str \| None` | Telegram username |
| `first_name` | `str \| None` | First name |
| `last_name` | `str \| None` | Last name |
| `language_code` | `str \| None` | IETF language code |
| `auth_date` | `int` | Unix timestamp of auth |

---

## Events

### Event

```python
from forgeapi import Event
```

Base class for all application events. Subclass to define your own event types.

```python
class Event:
    background: ClassVar[bool] = False   # True = fire-and-forget
    redis: ClassVar[bool] = False        # True = publish to Redis pub/sub
    ttl: ClassVar[int | None] = None     # dedup window in seconds (Redis only)
```

Every instance automatically receives a unique `event_id` (UUID4) assigned in `__init__`.

#### Class variables

| Variable | Type | Default | Description |
|---|---|---|---|
| `background` | `bool` | `False` | `True` — `dispatch()` schedules listeners via `create_task` and returns immediately; response is not blocked |
| `redis` | `bool` | `False` | `True` — event is serialised and published to `forgeapi:events:<ClassName>` Redis channel; every subscribed worker runs its local listeners |
| `ttl` | `int \| None` | `None` | Deduplication window in seconds. Subscriber attempts `SET NX EX {ttl}` on `forgeapi:dedup:{event_id}`. Only the first worker to acquire the key processes the event |

#### Instance attributes

| Attribute | Type | Description |
|---|---|---|
| `event_id` | `str` | UUID4 string auto-assigned at construction. Preserved through Redis serialisation so all workers share the same ID |

#### Methods

##### `await event.dispatch() -> None`

Fires the event through the singleton `EventBus`.

- `redis=False`: runs all registered listeners locally, in parallel via `asyncio.gather`.
- `redis=True`: publishes the serialised event to Redis. The subscriber on each worker deserialises it and runs local listeners.
- `background=True`: wraps the gather in `asyncio.create_task` so the caller is not blocked.
- `background=False`: awaits the gather — all listeners finish before `dispatch()` returns.

Listener exceptions are **caught and logged individually** — one failing listener does not stop others or bubble up to the route.

##### `event.to_dict() -> dict`

Serialises the event to a plain `dict` for Redis transport. Default implementation converts all public instance attributes (including `event_id`). Override for non-JSON-serialisable fields:

```python
class OrderCreated(Event):
    redis = True

    def __init__(self, order_id: int, items: list) -> None:
        self.order_id = order_id
        self.items = items   # list of ORM objects

    def to_dict(self) -> dict:
        base = super().to_dict()
        base["items"] = [{"id": i.id, "name": i.name} for i in self.items]
        return base
```

##### `Event.from_dict(data: dict) -> Event`

Class method. Reconstructs an event from its serialised dict. Called by the Redis subscriber on each receiving worker. Default implementation creates a new instance and sets all dict keys as attributes. Override when you need typed reconstruction:

```python
    @classmethod
    def from_dict(cls, data: dict) -> "OrderCreated":
        obj = cls.__new__(cls)
        obj.event_id  = data["event_id"]
        obj.order_id  = data["order_id"]
        obj.items     = data["items"]   # plain dicts on the receiving side
        return obj
```

#### Full example

```python
# app/events/order_shipped_event.py
from forgeapi import Event

class OrderShipped(Event):
    background = True   # don't block the response
    redis = True        # fan out to all workers
    ttl = 300           # one worker handles per 5 min (dedup by order_id not needed — event_id is unique per dispatch)

    def __init__(self, order_id: int, carrier: str) -> None:
        self.order_id = order_id
        self.carrier  = carrier

# --- dispatching ---
await OrderShipped(order_id=42, carrier="DHL").dispatch()
```

---

### EventBus

```python
from forgeapi import EventBus
```

Singleton event dispatcher. Interact directly only for manual registration, Redis wiring, or testing.

#### Class methods

##### `EventBus.get_instance() -> EventBus`

Returns the process-wide singleton. Creates it on first call.

##### `EventBus.reset() -> None`

Destroys the singleton and clears all registrations. Required in tests to prevent listener bleed-through.

```python
@pytest.fixture(autouse=True)
def reset_bus():
    EventBus.reset()
    yield
    EventBus.reset()
```

#### Instance methods

##### `bus.register(event_class: type, listener: Callable) -> None`

Register a listener without a decorator.

```python
bus = EventBus.get_instance()
bus.register(OrderShipped, my_handler)
```

`listener` must be an `async def` function. Registering a sync function raises `TypeError` immediately.

##### `bus.listeners_for(event_class: type) -> list[Callable]`

Return all listeners registered for a given event class (does not include subclasses).

```python
listeners = bus.listeners_for(OrderShipped)
# → [notify_warehouse, update_analytics]
```

##### `bus.on(event_class: type)`

Decorator. Identical to `@listen` but called on the instance. See [@bus.on](#buson).

##### `bus.set_redis(client) -> None`

Attach a `redis.asyncio` client. Required before dispatching any `redis=True` event.

```python
import redis.asyncio as aioredis
bus.set_redis(aioredis.from_url("redis://localhost:6379"))
```

##### `await bus.start_redis_subscriber() -> None`

Long-running coroutine. Subscribes to `forgeapi:events:*` and dispatches received events to local listeners. Run as a background task in the app lifespan:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    redis_client = aioredis.from_url("redis://localhost:6379")
    bus = EventBus.get_instance()
    bus.set_redis(redis_client)
    task = asyncio.create_task(bus.start_redis_subscriber())
    yield
    task.cancel()
    await redis_client.aclose()
```

##### `bus.load_from_dir(directory: str) -> None`

Import all `*.py` files in `directory`. Listeners registered via `@listen` or `@bus.on` inside those files are activated on import. Called automatically by `Core(app, events=True)`.

##### `bus._bg_tasks: list[asyncio.Task]`

Internal list of background tasks created by `background=True` dispatches. Useful in tests to await all scheduled work:

```python
await asyncio.gather(*bus._bg_tasks, return_exceptions=True)
```

---

### @listen

```python
from forgeapi import listen
```

Decorator. Registers an `async def` function as a listener for a specific event class **at import time**. Registering a sync function raises `TypeError`.

```python
@listen(UserRegistered)
async def send_welcome_email(event: UserRegistered) -> None:
    await mailer.send(event.email)

@listen(UserRegistered)
async def create_default_settings(event: UserRegistered) -> None:
    await Settings.create(user_id=event.user_id)
```

Multiple `@listen` decorators for the same event class all run in **parallel** via `asyncio.gather` when the event is dispatched. Exception from one listener is logged but does not cancel the others.

> **Do not use `@listen` at module level inside test files.** Listeners registered at import time are attached to the singleton that existed at import time. When `EventBus.reset()` creates a new singleton in a fixture, those top-level listeners become invisible. Always register listeners inside the test body or a fixture.

---

### @bus.on

```python
from forgeapi import EventBus
bus = EventBus.get_instance()

@bus.on(OrderShipped)
async def notify_warehouse(event: OrderShipped) -> None:
    await warehouse_api.notify(event.order_id)
```

Instance-based alternative to `@listen`. Functionally identical — registers on the same process-wide singleton. Prefer `@listen` in listener files that are auto-loaded by `Core`; prefer `@bus.on` when you hold an explicit `bus` reference.

Both decorators accept the same event class and the same restriction: only `async def` functions.

---

## RedisBus

```python
from forgeapi import RedisBus
from forgeapi.events import RedisBus
```

Standalone Redis pub/sub bus for cross-project communication. Each project creates its own instance — no shared Python code needed between them.

```python
RedisBus(
    url: str,
    namespace: str = "forge",
)
```

### Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `url` | `str` | — | Redis connection URL, e.g. `"redis://localhost:6379"` |
| `namespace` | `str` | `"forge"` | Channel prefix. Same namespace in both projects = shared events. Different namespace = isolated. |

Redis channel format: `{namespace}:{channel}` — e.g. `shop:order:created`.

### `bus.on(channel)`

Decorator. Register an async handler for a named channel. Multiple handlers on the same channel all run in parallel.

```python
bus = RedisBus("redis://localhost:6379", namespace="shop")

@bus.on("order:created")
async def handle_order(data: dict) -> None:
    await telegram.send(f"Order #{data['id']}")

@bus.on("order:created")
async def log_order(data: dict) -> None:
    logger.info("order: %s", data)
```

Handlers receive a plain `dict`. No shared event classes needed between projects.

### `await bus.emit(channel, data)`

Publish `data` to `channel`.

`data` accepts:

| Type | Behaviour |
|---|---|
| `dict` | Used as-is |
| Tortoise ORM model | Scalar fields serialised automatically; un-fetched relations skipped |
| Any object with `__dict__` | Public attributes serialised |

Non-JSON types are converted automatically:

| Python type | JSON |
|---|---|
| `datetime`, `date` | ISO 8601 string |
| `Decimal` | `float` |
| `UUID` | string |

```python
# plain dict
await bus.emit("order:created", {"id": 42, "total": 99.9})

# Tortoise model — scalar fields only
order = await Order.get(id=42)
await bus.emit("order:created", order)

# prefetch relations to include them in the payload
order = await Order.get(id=42).prefetch_related("items")
await bus.emit("order:created", order)
```

Raises `RuntimeError` if called before `connect()`.

### `await bus.listen()`

Coroutine. Subscribes to all channels in the namespace and dispatches incoming messages to registered handlers. Runs indefinitely until cancelled.

Safe inside an existing asyncio event loop — does **not** create a new one.

```python
task = asyncio.create_task(bus.listen())
# on shutdown:
task.cancel()
```

### `await bus.connect()` / `await bus.disconnect()`

Open and close the Redis connection manually. Called automatically by the context manager.

### Context manager — `async with bus:`

Connects, starts `listen()` as a background task, cleans up on exit.

```python
# FastAPI lifespan
@asynccontextmanager
async def lifespan(app: FastAPI):
    async with bus:
        yield

# standalone script
async def main():
    async with bus:
        await asyncio.sleep(float("inf"))

asyncio.run(main())
```

### Full cross-project example

**Project A** — e-commerce backend:

```python
# bus.py
from forgeapi import RedisBus
bus = RedisBus("redis://localhost:6379", namespace="shop")

@bus.on("notification:sent")
async def on_notification(data: dict) -> None:
    await Order.filter(id=data["order_id"]).update(notified=True)

# order_controller.py
@route.post("/orders", status_code=201)
async def create(self, payload: OrderCreate, user: CurrentUser):
    order = await Order.create(**payload.model_dump(), user_id=int(user.id))
    await bus.emit("order:created", order)   # Tortoise model → dict automatically
    return order
```

**Project B** — notification service:

```python
# bus.py
from forgeapi import RedisBus
bus = RedisBus("redis://localhost:6379", namespace="shop")

@bus.on("order:created")
async def on_order(data: dict) -> None:
    await telegram.send(chat_id=ADMIN_CHAT, text=f"New order #{data['id']}")
    await bus.emit("notification:sent", {"order_id": data["id"]})
```

**Both projects — identical lifespan wiring:**

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from .bus import bus

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with bus:
        yield

app = FastAPI(lifespan=lifespan)
```

### `RedisBus` vs `EventBus`

| | `EventBus` | `RedisBus` |
|---|---|---|
| Scope | Same project, multiple workers | Different projects on same Redis |
| Channel key | Python event class | String |
| Payload received | Typed `Event` object | Plain `dict` |
| Shared Python code | Required (event classes) | Not required |
| Redis required | Optional (`set_redis()`) | Always |
| Deduplication | `ttl` class var + SET NX | Not built-in |

---

## Controllers

### Controller

```python
from forgeapi import Controller
```

Base controller class. Auto-registers methods decorated with `@route` into an `APIRouter`. Controllers are discovered and mounted automatically by `Core(app, controllers=True)`.

```python
class Controller:
    prefix: str = ""        # auto-derived from class name if not set
    tags: list[str] = []    # auto-derived from prefix if not set
    guards: list = []       # applied as router-level dependencies
```

#### Auto-derived prefix

| Class name | Prefix |
|---|---|
| `UserController` | `/users` |
| `AdminUserController` | `/admin/users` |
| `PostCommentController` | `/post/comments` |

#### Example

```python
# app/controllers/user_controller.py
from forgeapi import Controller, route, CurrentUser
from app.schemas import UserSchema, UserCreateSchema

class UserController(Controller):
    prefix = "/users"
    tags = ["Users"]

    @route.get("/")
    async def index(self) -> list[UserSchema]:
        return await User.all()

    @route.get("/{id}")
    async def show(self, id: int) -> UserSchema:
        return await User.get_or_none(id=id)

    @route.post("/")
    async def store(self, payload: UserCreateSchema, user: CurrentUser) -> UserSchema:
        return await User.create(**payload.model_dump())

    @route.delete("/{id}")
    async def destroy(self, id: int) -> None:
        await User.filter(id=id).delete()
```

---

### route

```python
from forgeapi import route
```

Decorator factory. Marks a `Controller` method as a route handler.

#### Shorthands

```python
@route.get(path, **kwargs)
@route.post(path, **kwargs)
@route.put(path, **kwargs)
@route.patch(path, **kwargs)
@route.delete(path, **kwargs)
```

#### Explicit form

```python
@route("/", methods=["GET", "POST"], response_model=MySchema, status_code=201)
```

All FastAPI `add_api_route` keyword arguments (`response_model`, `status_code`, `dependencies`, `summary`, etc.) are passed through.

```python
@route.post("/", status_code=201, response_model=UserSchema)
async def store(self, payload: UserCreateSchema) -> UserSchema:
    ...

@route.delete("/{id}", dependencies=[Depends(ApiKeyGuard())])
async def destroy(self, id: int) -> None:
    ...
```

---

## Middleware

### Middleware

```python
from forgeapi import Middleware
```

Base class for custom global middleware. Wraps Starlette's `BaseHTTPMiddleware`.

```python
class Middleware:
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        return await call_next(request)
```

Register via `Core(app, middleware=[MyMiddleware])` or `core.use()`:

```python
class TimingMiddleware(Middleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        import time
        start = time.perf_counter()
        response = await call_next(request)
        response.headers["X-Process-Time"] = f"{time.perf_counter() - start:.3f}s"
        return response

# Option 1 — at Core init
Core(app, middleware=[TimingMiddleware])

# Option 2 — with kwargs
class TenantMiddleware(Middleware):
    def __init__(self, app, default_tenant: str = "public"):
        super().__init__(app)
        self.default_tenant = default_tenant

    async def dispatch(self, request, call_next):
        request.state.tenant = request.headers.get("X-Tenant", self.default_tenant)
        return await call_next(request)

core.use(TenantMiddleware, default_tenant="acme")
```

---

### Guard

```python
from forgeapi import Guard
```

DI-based per-route or per-controller middleware. Declare parameters in `handle` — FastAPI injects them automatically, the same way as a route handler.

```python
class Guard:
    async def handle(self) -> None:
        pass
```

#### Per-route

```python
from fastapi import Depends, HTTPException, Request
from forgeapi import Guard

class ApiKeyGuard(Guard):
    def __init__(self, header: str = "X-API-Key"):
        self.header = header

    async def handle(self, request: Request) -> None:
        if not request.headers.get(self.header):
            raise HTTPException(403, "Missing API key")

@route.post("/webhook", dependencies=[Depends(ApiKeyGuard())])
async def webhook(self, payload: dict) -> None:
    ...
```

#### Per-controller (applies to every route in the controller)

```python
from forgeapi import Guard
from forgeapi.auth import CurrentUser

class ActiveUserGuard(Guard):
    async def handle(self, user: CurrentUser) -> None:
        db_user = await User.get_or_none(id=user.id)
        if not db_user or not db_user.is_active:
            raise HTTPException(403, "Account disabled")

class UserController(Controller):
    guards = [ActiveUserGuard()]
    ...
```

---

## Permissions

Spatie-style polymorphic roles and permissions. Uses two shared tables (`model_has_roles`, `model_has_permissions`) — no per-model junction tables.

**Setup:** Add `"forgeapi.permissions.models"` to your Tortoise `apps` config and run migrations.

### PermissionsMixin

```python
from forgeapi.permissions import PermissionsMixin
```

Abstract Tortoise model mixin. Add to any model to get roles and permissions.

```python
from forgeapi.permissions import PermissionsMixin
from tortoise import fields

class User(PermissionsMixin):
    id    = fields.IntField(pk=True)
    email = fields.CharField(max_length=255, unique=True)

    class Meta:
        table = "users"
```

All check methods accept an optional `guard: str = "api"` keyword argument that scopes lookups to a specific auth guard, preventing cross-guard permission leakage. The result of `get_all_permissions()` is cached per-instance per guard and invalidated automatically on any mutation.

#### Permission methods

| Method | Returns | Description |
|---|---|---|
| `await user.can(*perms, guard="api")` | `bool` | `True` if user has **any** of the permissions (direct or via role). Runs two DB queries in parallel. |
| `await user.cannot(*perms, guard="api")` | `bool` | Inverse of `can()` |
| `await user.has_all_permissions(*perms, guard="api")` | `bool` | `True` only if user has **all** permissions |
| `await user.get_all_permissions(guard="api")` | `list[str]` | All permission names (direct + via roles, deduplicated). Result is cached for the lifetime of the instance. |
| `await user.give_permission(*perms)` | `None` | Grant direct permissions. Clears the permission cache. |
| `await user.revoke_permission(*perms)` | `None` | Revoke direct permissions. Clears the permission cache. |

#### Role methods

| Method | Returns | Description |
|---|---|---|
| `await user.has_role(*roles, guard="api")` | `bool` | `True` if user has **any** of the roles |
| `await user.has_all_roles(*roles, guard="api")` | `bool` | `True` only if user has **all** roles (deduplicates input before comparing) |
| `await user.get_role_names()` | `list[str]` | All role names |
| `await user.assign_role(*roles)` | `None` | Assign roles (creates if not exist). Clears the permission cache. |
| `await user.remove_role(*roles)` | `None` | Remove roles. Clears the permission cache. |

#### Class-level filters

Both accept an optional `guard: str = "api"` keyword to filter roles by guard.

```python
# QuerySet of users who have any of the given roles
qs = await User.with_role("admin", "moderator")
qs = await User.with_role("admin", guard="web")

# QuerySet of users who have none of the given roles
qs = await User.without_role("banned")
```

#### Usage examples

```python
user = await User.get(id=1)

await user.assign_role("editor")
await user.give_permission("publish:posts", "delete:comments")

print(await user.can("publish:posts"))           # True
print(await user.can("publish:posts", guard="api"))  # scoped check
print(await user.has_role("editor"))             # True
print(await user.get_all_permissions())          # ["publish:posts", "delete:comments", ...]
```

---

### Permission

```python
from forgeapi.permissions import Permission
```

Tortoise model for individual permissions.

| Field | Type | Description |
|---|---|---|
| `id` | `int` | Primary key |
| `name` | `str` | Unique permission name, e.g. `"edit:posts"` |
| `guard` | `str` | Guard name, defaults to `"api"` |

```python
# Find or create
perm = await Permission.find_or_create("publish:posts")

# Role-level permission management
role = await Role.find_or_create("editor")
await role.give_permission("edit:posts", "publish:posts")
await role.revoke_permission("delete:posts")
print(await role.has_permission("edit:posts"))            # True
print(await role.has_permission("edit:posts", guard="web"))  # scoped to guard
```

---

### Role

```python
from forgeapi.permissions import Role
```

Tortoise model. Roles group permissions and can be assigned to any model.

| Field | Type | Description |
|---|---|---|
| `id` | `int` | Primary key |
| `name` | `str` | Unique role name, e.g. `"admin"` |
| `guard` | `str` | Guard name, defaults to `"api"` |
| `permissions` | `M2M` | Many-to-many relation to `Permission` |

#### Role methods

| Method | Description |
|---|---|
| `await role.give_permission(*names)` | Add permissions to the role |
| `await role.revoke_permission(*names)` | Remove permissions from the role |
| `await role.has_permission(name, guard="api")` | Check if role has a specific permission (scoped by guard) |

---

### require_permission / RequirePermission

```python
from forgeapi.permissions import require_permission
# Alias kept for backward compatibility
from forgeapi.permissions import RequirePermission
```

FastAPI dependency factory. Raises `401` for an invalid or inactive user, `403` (detail: `"Forbidden"`) if the check fails. On success, injects the DB user instance.

The user model is resolved from `request.app.state.user_model` first, falling back to the global registry set by `Core`.

```python
require_permission(*permissions: str)
```

```python
@route.delete("/{id}")
async def destroy(self, id: int, user=require_permission("delete:posts")):
    await Post.filter(id=id).delete()

# User must have AT LEAST ONE of the permissions
@route.post("/")
async def store(self, payload: PostCreate, user=require_permission("create:posts", "admin")):
    ...
```

---

### require_role / RequireRole

```python
from forgeapi.permissions import require_role
# Alias kept for backward compatibility
from forgeapi.permissions import RequireRole
```

FastAPI dependency factory. Raises `401` for an invalid or inactive user, `403` (detail: `"Forbidden"`) if the check fails. On success, injects the DB user instance.

```python
require_role(*roles: str)
```

```python
@route.get("/admin/stats")
async def stats(self, user=require_role("admin")):
    ...

# User must have AT LEAST ONE of the roles
@route.get("/dashboard")
async def dashboard(self, user=require_role("admin", "moderator")):
    ...
```

---

## Schemas

```python
from forgeapi import BaseSchema, BaseCreateSchema, BaseUpdateSchema
```

Pydantic v2 base schemas for common patterns.

### BaseSchema

For response models. Reads from Tortoise ORM models via `from_attributes = True`.

```python
class BaseSchema(BaseModel):
    id: int
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}
```

```python
class UserSchema(BaseSchema):
    username: str
    email: str

@route.get("/{id}", response_model=UserSchema)
async def show(self, id: int):
    return await User.get(id=id)
```

### BaseCreateSchema

For POST (create) request bodies. All fields should be required.

```python
class UserCreateSchema(BaseCreateSchema):
    username: str
    email: str
    password: str
```

### BaseUpdateSchema

For PATCH (update) request bodies. All fields should be `Optional` for partial updates.

```python
class UserUpdateSchema(BaseUpdateSchema):
    username: str | None = None
    email: str | None = None
```

---

## Settings

```python
from forgeapi import BaseAppSettings
```

Pydantic Settings base class. Reads from environment variables and `.env` file automatically.

```python
class BaseAppSettings(BaseSettings):
    debug: bool = False
    app_name: str = "FastAPI App"
    # env_file=".env" is configured automatically
```

Extend with your own fields:

```python
from forgeapi import BaseAppSettings

class Settings(BaseAppSettings):
    database_url: str
    redis_url: str | None = None
    jwt_secret: str
    debug: bool = False
    allowed_hosts: list[str] = ["*"]

settings = Settings()  # reads .env automatically
```

Any field can be overridden by an environment variable with the same name (case-insensitive). Extra environment variables are ignored.

---

## Pagination

```python
from forgeapi.pagination import Paginator, Pagination
```

### Paginator

FastAPI dependency class. Extracts `?page` and `?limit` from query parameters.

```python
class Paginator:
    DEFAULT_LIMIT: ClassVar[int] = 20   # override via configure()
    MAX_LIMIT: ClassVar[int] = 100

    page: int     # current page (1-based)
    limit: int    # resolved items per page (clamped to MAX_LIMIT)
    offset: int   # (page - 1) * limit
```

#### `Paginator.configure(default_limit, max_limit)`

Update class-level defaults for all future instances.

```python
Paginator.configure(default_limit=10, max_limit=50)
# or via Core:
Core(app, pagination=10)
```

### Pagination

Type alias: `Annotated[Paginator, Depends()]`. Use as an annotation directly.

```python
from forgeapi.pagination import Pagination

@router.get("/products")
async def list_products(pagination: Pagination):
    total = await Product.all().count()
    items = (
        await Product.all()
        .offset(pagination.offset)
        .limit(pagination.limit)
    )
    return {
        "items": items,
        "total": total,
        "page": pagination.page,
        "limit": pagination.limit,
    }
```

Query string:

```
GET /products?page=2&limit=50
```

---

## Seeder

```python
from forgeapi.database import Seeder
```

Base class for database seeders. Subclass and implement `run()`.

```python
class Seeder:
    async def run(self) -> None:
        raise NotImplementedError
```

#### Example

```python
# database/seeds/user_seeder.py
from forgeapi.database import Seeder
from app.models import User

class UserSeeder(Seeder):
    async def run(self) -> None:
        await User.get_or_create(
            username="admin",
            defaults={
                "email": "admin@example.com",
                "password_hash": hash_password("admin123"),
                "is_active": True,
            },
        )
```

Run seeders with the CLI:

```bash
forge seed
forge seed UserSeeder      # run a specific seeder
forge seed --fresh         # truncate tables first
```

---

## Telescope

```python
from forgeapi.telescope import setup_telescope, record_job, DebugStore
```

In-process request debugger. Captures every HTTP request — headers, body, SQL queries, log records, dispatched events, and custom job runs — and streams them to connected WebSocket clients in real time. Activated automatically by `Core(app, debug=True)`.

---

### setup_telescope

```python
setup_telescope(app: FastAPI) -> None
```

Installs all Telescope hooks and mounts the WebSocket router on `app`. Called automatically by `Core(app, debug=True)`. Safe to call multiple times — all hooks are idempotent.

What it installs:

| Component | Description |
|---|---|
| `DebugMiddleware` | Pure-ASGI middleware that buffers request/response bodies and creates a `RequestEntry` per HTTP request |
| `DebugLogHandler` | `logging.Handler` added to the root logger; captures all log records during a request |
| `EventBus.dispatch` patch | Wraps `dispatch()` to record dispatched events in the active entry |
| Tortoise SQL hooks | Wraps `execute_*` methods on all `BaseDBAsyncClient` subclasses to record SQL queries |
| `/_forge/telescope/ws` | WebSocket endpoint for live streaming |

---

### record_job

```python
from forgeapi.telescope import record_job

record_job(
    job: str,
    status: str,
    attempts: int = 1,
    duration_ms: float | None = None,
    error: str | None = None,
) -> None
```

Attach a custom job execution record to the active Telescope entry. Call from your job dispatcher or runner so Telescope shows which background jobs were triggered during a request.

Is a no-op (silent) when called outside an active Telescope request context.

| Parameter | Type | Description |
|---|---|---|
| `job` | `str` | Job class name or any identifier |
| `status` | `str` | `"queued"` \| `"running"` \| `"done"` \| `"failed"` |
| `attempts` | `int` | Number of attempts made (default `1`) |
| `duration_ms` | `float \| None` | Execution time in milliseconds; `None` if not yet finished |
| `error` | `str \| None` | Exception message when `status == "failed"` |

```python
import time
from forgeapi.telescope import record_job

async def send_invoice(order_id: int) -> None:
    t = time.perf_counter()
    try:
        await pdf.generate(order_id)
        record_job("SendInvoice", status="done", attempts=1,
                   duration_ms=round((time.perf_counter() - t) * 1000, 3))
    except Exception as exc:
        record_job("SendInvoice", status="failed", attempts=1, error=str(exc))
        raise
```

---

### DebugStore

```python
from forgeapi.telescope.store import DebugStore
```

In-memory circular store. Holds at most `_MAX_ENTRIES` (200) `RequestEntry` objects. Class-level — there is one store per process.

#### Class methods

##### `DebugStore.new_entry(...) -> RequestEntry`

Factory. Creates a new `RequestEntry` with the given fields and a fresh UUID `id`. Does not add it to the store.

```python
DebugStore.new_entry(
    method: str,
    path: str,
    query_string: str = "",
    headers: dict | None = None,
    payload: Any = None,
) -> RequestEntry
```

##### `DebugStore.push(entry: RequestEntry) -> None`

Adds an entry to the store. Evicts the oldest entry when the buffer is full (also removes it from the index). Broadcasts `{"type": "entry", ...}` to all connected WebSocket clients as an `asyncio.Task`.

##### `DebugStore.all() -> list[RequestEntry]`

Returns all stored entries, newest first.

##### `DebugStore.get(entry_id: str) -> RequestEntry | None`

O(1) lookup by entry UUID. Returns `None` if not found.

##### `DebugStore.clear() -> None`

Replaces `_store` and `_index` with fresh empty objects (atomic — no partial state visible to concurrent `push()`). Broadcasts `{"type": "clear"}` to all connected clients.

---

### RequestEntry

```python
from forgeapi.telescope.store import RequestEntry
```

Dataclass representing one captured HTTP request.

| Field | Type | Description |
|---|---|---|
| `id` | `str` | UUID4 |
| `method` | `str` | HTTP method |
| `path` | `str` | Request path |
| `query_string` | `str` | Raw query string |
| `headers` | `dict[str, str]` | Request headers (sensitive values masked) |
| `payload` | `Any` | Parsed request body (sensitive fields masked; capped at 64 KB) |
| `timestamp` | `str` | ISO 8601 UTC |
| `status` | `int \| None` | Response status code |
| `duration_ms` | `float \| None` | Total handler duration |
| `response_body` | `Any` | Parsed response body (masked; capped at 64 KB) |
| `queries` | `list[SqlRecord]` | SQL queries fired during the request |
| `logs` | `list[LogRecord]` | Log records emitted during the request |
| `events` | `list[EventRecord]` | Events dispatched during the request |
| `jobs` | `list[JobRecord]` | Job executions recorded via `record_job()` |

#### `entry.summary() -> dict`

Returns a lightweight dict with `id`, `method`, `path`, `status`, `duration_ms`, `timestamp`, and a `counts` dict with the lengths of `queries`, `logs`, `events`, `jobs`.

#### `entry.to_dict() -> dict`

Full serialisation of all fields, with `datetime` / `date` values converted to ISO 8601 strings. Sent in the WebSocket `entry` message.

---

### Record types

#### `SqlRecord`

| Field | Type | Description |
|---|---|---|
| `sql` | `str` | Raw SQL string |
| `params` | `Any` | Bound parameters (may be `None`) |
| `duration_ms` | `float` | Query execution time |
| `location` | `str` | `file.py:line in function_name` — first non-framework frame |

Failed queries (those that raised an exception) are recorded via `try/finally` — the record is always appended.

#### `LogRecord`

| Field | Type | Description |
|---|---|---|
| `level` | `str` | e.g. `"INFO"`, `"WARNING"` |
| `logger` | `str` | Logger name |
| `message` | `str` | Formatted message |
| `time` | `str` | Formatted time string |

Loggers whose name equals or starts with `"forgeapi.telescope"` or `"forgeapi.access"` are excluded to prevent recursion.

#### `EventRecord`

| Field | Type | Description |
|---|---|---|
| `event` | `str` | Event class name |
| `listeners` | `list[str]` | Names of all registered listeners |
| `background` | `bool` | Whether the event has `background=True` |

#### `JobRecord`

| Field | Type | Description |
|---|---|---|
| `job` | `str` | Job identifier |
| `status` | `str` | `"queued"` \| `"running"` \| `"done"` \| `"failed"` |
| `attempts` | `int` | Attempt count |
| `duration_ms` | `float \| None` | Execution time |
| `error` | `str \| None` | Error message on failure |

---

### ConnectionManager

```python
from forgeapi.telescope.store import manager
```

Manages live WebSocket connections. The module-level `manager` singleton is shared by the router and the store.

| Method | Description |
|---|---|
| `await manager.connect(ws)` | Accepts the WebSocket and registers it. Rejects with code `1008` when the cap of 100 connections is reached |
| `manager.disconnect(ws)` | Removes the WebSocket from the active list |
| `await manager.broadcast(payload)` | Sends JSON to all active connections. Dead sockets are removed automatically |

---

### DebugMiddleware

```python
from forgeapi.telescope.middleware import DebugMiddleware
```

Pure-ASGI middleware (not Starlette `BaseHTTPMiddleware`). Runs in the same asyncio task as the request so `ContextVar` is visible to all hooks without `copy_context()`.

Behaviour per request:

1. Skip Telescope and docs paths entirely.
2. Buffer the **full** request body (needed for replay), but pass only the first 64 KB to `_parse_payload` for storage.
3. Create a `RequestEntry` via `DebugStore.new_entry()` and set it as the `ContextVar` current entry.
4. Wrap `send` to capture response status and body chunks (capped at 64 KB total).
5. Call the inner app.
6. In `finally`: write `duration_ms`, `status`, `response_body` into the entry and call `DebugStore.push()`.

---

### Hooks

#### `install_tortoise_hook() -> None`

```python
from forgeapi.telescope.hooks.tortoise_hook import install_tortoise_hook
```

Patches `execute_query`, `execute_insert`, `execute_many`, `execute_script` on all `BaseDBAsyncClient` subclasses already imported, and installs an `__init_subclass__` hook to patch classes imported later.

- Uses `sys._getframe()` (not `traceback.extract_stack()`) for O(1) frame walking without `FrameSummary` allocation.
- Wraps each query in `try/finally` so failed queries are still recorded.
- Safe to call multiple times — guarded by `_INSTALLED` flag.

#### `install_events_hook() -> None`

```python
from forgeapi.telescope.hooks.events_hook import install_events_hook
```

Monkeypatches `EventBus.dispatch`. The recording block is wrapped in `try/except` so a hook failure never prevents the actual dispatch from running.

#### `install_logging_hook() -> None`

```python
from forgeapi.telescope.hooks.logging_hook import install_logging_hook
```

Adds a `DebugLogHandler` to the root logger. Skip check uses prefix matching (`name == prefix or name.startswith(prefix + ".")`) so sub-loggers like `forgeapi.telescope.sql` are also excluded.
