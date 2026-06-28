# ForgeAPI — Documentation

## Table of Contents

1. [Quick start](#1-quick-start)
2. [Project structure](#2-project-structure)
3. [Core](#3-core)
4. [Auth](#4-auth)
   - [How it works](#how-it-works)
   - [CurrentUser and OptionalUser](#currentuser-and-optionaluser)
   - [JWT strategy](#jwt-strategy)
   - [Cookie strategy](#cookie-strategy)
   - [Telegram strategy](#telegram-strategy)
5. [Pagination](#5-pagination)
6. [Events](#6-events)
   - [Defining events](#defining-events)
   - [@listen decorator](#listen-decorator)
   - [Dispatching](#dispatching)
   - [EventBus](#eventbus)
7. [Controllers](#7-controllers)
   - [Base pattern](#base-pattern)
   - [Route decorator](#route-decorator)
   - [Auto-prefix and namespace](#auto-prefix-and-namespace)
8. [Schemas](#8-schemas)
   - [Base classes](#base-classes)
   - [Schema directories](#schema-directories)
   - [generate:schema](#generateschema)
9. [Permissions](#9-permissions)
   - [Setup](#setup)
   - [PermissionsMixin](#permissionsmixin)
   - [Dependencies](#dependencies)
   - [Role and Permission models](#role-and-permission-models)
10. [Middleware](#10-middleware)
    - [CORS](#cors)
    - [Rate limiting](#rate-limiting)
    - [Request ID](#request-id)
    - [Access logging](#access-logging)
11. [Settings](#11-settings)
12. [CLI reference](#12-cli-reference)
13. [forgeapi.toml reference](#13-forgeapitoml-reference)

---

## 1. Quick start

```bash
pip install forge-kits
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
    auth=True,           # auth strategy
    cors=["*"],          # CORS origins
    rate_limit=60,       # requests per minute
    pagination=20,       # default page size
    request_id=True,     # X-Request-ID header
    events=True,         # auto-load listeners
    permissions=User,    # enable permissions (pass your User model)
    logging=True,        # access log (default True)
    controllers=True,    # auto-discover controllers (default True)
    debug=False,         # debug mode — relaxes security checks
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
| `permissions` | `Type \| None` | `None` | Pass your User model class to enable `RequirePermission`/`RequireRole` |
| `logging` | `bool` | `True` | Logs method + path + status + duration for every request |
| `controllers` | `bool` | `True` | Auto-imports `*_controller.py` (recursive) and registers routers |
| `debug` | `bool` | `False` | Debug mode — relaxes security checks (see below). **Never use in production.** |
| `config_path` | `str` | `"forgeapi.toml"` | Path to the TOML config file |

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

## 4. Auth

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

## 5. Pagination

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

```toml
[pagination]
default_limit = 20
max_limit     = 100
```

Or configure via `Core`:

```python
Core(app, pagination=20)    # default_limit=20, max_limit from toml
Core(app, pagination=True)  # both from toml
```

---

## 6. Events

Events decouple side effects (emails, notifications, cache) from business logic.

### Defining events

```python
# app/events/order_created_event.py
from forgeapi import Event

class OrderCreated(Event):
    background = True   # True = fire-and-forget; False = await before response

    def __init__(self, order_id: int, total: float) -> None:
        self.order_id = order_id
        self.total    = total
```

`background = True` — listeners run in `asyncio.create_task`, response is returned immediately.  
`background = False` (default) — all listeners are awaited before the response.

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

Multiple listeners for the same event run **in parallel** via `asyncio.gather`.  
Individual listener exceptions are logged but do **not** propagate to the route.

### Dispatching

```python
@route.post("/orders")
async def create(self, payload: OrderCreatePayload, user: CurrentUser) -> OrderResponse:
    order = await Order.create(**payload.model_dump(), user_id=int(user.id))
    await OrderCreated(order_id=order.id, total=order.total).dispatch()
    return OrderResponse.model_validate(order)
```

### EventBus

`Core(app, events=True)` calls `EventBus.load_from_dir("app/listeners")` which imports every `*.py` file in the directory. `@listen` registers on import — no manual wiring needed.

```python
from forgeapi import EventBus

# manual registration (without decorator)
bus = EventBus.get_instance()
bus.register(OrderCreated, my_async_handler)

# inspect registered listeners
listeners = bus.listeners_for(OrderCreated)

# reset (useful in tests)
EventBus.reset()
```

Test fixture:

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

## 7. Controllers

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

If `prefix` is not set, it is derived from the class name. Every CamelCase word before the last becomes a URL segment; the last word is pluralised:

| Class | Auto prefix |
|---|---|
| `UserController` | `/users` |
| `AdminUserController` | `/admin/users` |
| `ApiV1PostController` | `/api/v1/posts` |
| `SuperAdminOrderItemController` | `/super/admin/order/items` |

Namespace controllers are generated into subdirectories:

```bash
forgeapi make:controller AdminUser    # controllers/admin/user_controller.py
forgeapi make:controller ApiV1Post    # controllers/api/v1/post_controller.py
```

```
controllers/
  user_controller.py
  admin/
    __init__.py
    user_controller.py      # AdminUserController → /admin/users
  api/
    __init__.py
    v1/
      __init__.py
      post_controller.py    # ApiV1PostController → /api/v1/posts
```

`Core` discovers all of these automatically via recursive glob.

---

## 8. Schemas

### Base classes

```python
from forgeapi import BaseSchema, BaseCreateSchema, BaseUpdateSchema
```

**`BaseSchema`** — response schemas. Adds `id: int`, `created_at: datetime`, `updated_at: datetime`. Has `from_attributes=True` so it reads directly from Tortoise model instances.

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

**`BaseUpdateSchema`** — PATCH payloads. Plain `BaseModel` subclass. Convention: all fields `Optional`.

```python
class PostUpdatePayload(BaseUpdateSchema):
    title: str | None = None
    body:  str | None = None

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

## 9. Permissions

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

```python
await user.can("edit:posts")                      # True if has ANY of the given perms (direct or via role)
await user.can("edit:posts", "admin")             # True if has ANY one of the two
await user.cannot("delete:users")                 # inverse of can()
await user.has_all_permissions("read", "write")   # True only if has ALL

await user.get_all_permissions()
# → ["edit:posts", "admin", ...]   direct + via roles, deduplicated
```

#### Granting / revoking permissions

```python
await user.give_permission("edit:posts", "delete:posts")
await user.revoke_permission("delete:posts", "edit:posts")   # one or many
await user.sync_permissions(["read:posts", "edit:posts"])    # replaces all direct perms
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
await user.sync_roles(["admin"])             # replaces all roles
```

---

### Dependencies

Enforce access control in route handlers. Both return the DB user instance on success or raise `403`.

```python
from forgeapi.permissions import RequirePermission, RequireRole
```

**`RequirePermission(*permissions)`** — user must have **at least one**:

```python
@route.delete("/{id}")
async def destroy(self, id: int, user=RequirePermission("delete:posts")):
    ...

@route.post("/")
async def create(self, payload: PostCreatePayload, user=RequirePermission("create:posts", "admin")):
    ...
```

**`RequireRole(*roles)`** — user must have **at least one**:

```python
@route.get("/admin/stats")
async def stats(self, user=RequireRole("admin")):
    ...

@route.get("/dashboard")
async def dashboard(self, user=RequireRole("admin", "moderator")):
    ...
```

---

### Role model

`Role` itself can have permissions — useful for bulk assignment.

```python
from forgeapi.permissions.models import Role, Permission

role = await Role.find_or_create("editor")

await role.give_permission("edit:posts", "read:posts")
await role.revoke_permission("read:posts")
await role.sync_permissions(["edit:posts"])
await role.has_permission("edit:posts")   # → bool

# assigning a role gives the user all permissions of that role
await user.assign_role("editor")
await user.can("edit:posts")   # → True (via role)
```

---

## 10. Middleware

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

## 11. Settings

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

---

## 12. CLI reference

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

---

### `forgeapi make:controller <Name> [flags]`

Generate a controller. CamelCase namespace supported.

```bash
forgeapi make:controller User
forgeapi make:controller User --ms            # + model + stub schemas
forgeapi make:controller AdminUser            # controllers/admin/user_controller.py
forgeapi make:controller ApiV1Post --ms
```

| Flag | Short | Generates |
|---|---|---|
| `--model` | `-m` | Tortoise model |
| `--schema` | `-s` | Stub schemas |

Compound: `--ms` `--mc` `--mcs` `-ms` `-cs` etc.

---

### `forgeapi make:model <Name> [flags]`

```bash
forgeapi make:model Post
forgeapi make:model Post -cs    # + controller + schema
```

| Flag | Short | Generates |
|---|---|---|
| `--controller` | `-c` | Controller |
| `--schema` | `-s` | Stub schemas |

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
forgeapi db:fresh             # TRUNCATE all tables (asks confirmation)
```

---

## 13. forgeapi.toml reference

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
