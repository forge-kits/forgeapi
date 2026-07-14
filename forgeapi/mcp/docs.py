from __future__ import annotations

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
access = auth.token(user)

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
- `core.auth` — the `Auth` facade instance, or `None`.
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
    schema = PostResponse      # auto response_model for all routes (skip 204)
    guards = [SomeGuard()]     # applied to EVERY route in this controller
```

## Auto-prefix derivation rules
- `PostController`              → `/posts`
- `AdminUserController`         → `/admin/users`
- `SuperAdminUserController`    → `/super/admin/users`
- `ApiV1ArticleController`      → `/api/v1/articles`

## Route decorators
```python
@route.get("/")
@route.post("/", status_code=201)
@route.put("/{id}")
@route.patch("/{id}")
@route.delete("/{id}", status_code=204)
```

## Full CRUD example
```python
class PostController(Controller):
    prefix = "/posts"
    tags   = ["posts"]
    schema = PostResponse      # auto response_model

    @route.get("/", response_model=None)   # override: returns paginated envelope
    async def index(self, request: Request) -> dict:
        return await Post.all().order_by("-created_at").paginate(request, PostResponse)

    @route.post("/", status_code=201)
    async def create(self, payload: PostCreatePayload) -> dict:
        return await Post.create_from(payload, author_id=1)

    @route.get("/{id}")
    async def show(self, id: int):
        return await Post.find_or_fail(id)

    @route.patch("/{id}")
    async def update(self, id: int, payload: PostUpdatePayload):
        post = await Post.find_or_fail(id)
        return await post.update_from(payload)

    @route.delete("/{id}", status_code=204)
    async def destroy(self, id: int):
        post = await Post.find_or_fail(id)
        await post.delete()
```

## ModelMixin shortcuts
```python
post = await Post.find_or_fail(id)          # 404 if not found
post = await Post.create_from(payload, author_id=user_id)
post = await post.update_from(payload)
```

## QuerySet .paginate()
```python
result = await Post.all().order_by("-created_at").paginate(request, PostResponse)
# Returns PaginatedResponse with data, meta (page/total/last_page), links (prev/next)
```

## Important rules
- Each request gets a **fresh** controller instance (no shared state across requests).
- Guards in `guards = [...]` are wrapped in `Depends()` automatically.
- The controller file must be named `*_controller.py` for auto-discovery to work.
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

## Listener via decorator
```python
from forgeapi import listen

@listen(MyEvent)
async def handle_my_event(event: MyEvent) -> None:
    await do_something(event.field1)
```

## Dispatch
```python
await MyEvent(field1=1, field2="hello").dispatch()
```

## Redis pub/sub (fan-out across workers)
```python
class OrderShipped(Event):
    background = True; redis = True; redis_type = "pubsub"; ttl = 300
    def __init__(self, order_id: int) -> None: self.order_id = order_id
```
Lifespan:
```python
@asynccontextmanager
async def lifespan(app):
    bus = EventBus.get_instance()
    await bus.redis_connect("redis://localhost:6379")
    task = asyncio.create_task(bus.start_redis_subscriber())
    yield
    task.cancel(); await bus.redis_disconnect()
```

## Redis Streams (persistent, consumer groups)
```python
class OrderEvent(Event):
    background = True; redis = True; redis_type = "stream"; namespace = "shop"
    def __init__(self, order_id: int, total: float) -> None:
        self.order_id = order_id; self.total = total
```

## RedisBus (cross-project, no shared Python classes)
```python
from forgeapi import RedisBus
bus = RedisBus("redis://localhost:6379", namespace="shop")

@bus.on("order:created")
async def handle(data: dict) -> None: await notify(data["id"])

await bus.emit("order:created", {"id": 1, "total": 99.0})
```

## Decision guide
- Local listeners: `redis=False` (default)
- Same-codebase multi-worker fan-out: `redis=True, redis_type="pubsub"`
- Cross-service or survives restart: `redis=True, redis_type="stream"`
- Cross-project no shared code: `RedisBus`

## Testing
```python
@pytest.fixture(autouse=True)
def reset_bus():
    EventBus.reset(); yield; EventBus.reset()
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

## Using in routes
```python
from forgeapi.auth import CurrentUser, OptionalUser

@route.get("/me")
async def me(self, user: CurrentUser) -> dict:
    return {"id": user.id, "username": user.username}

@route.get("/feed")
async def feed(self, user: OptionalUser) -> dict:
    if user: return personalised_feed(int(user.id))
    return public_feed()
```

## AuthUser fields
- `user.id: str` — JWT `sub` claim; use `int(user.id)` for DB queries
- `user.username: str | None`
- `user.extra: dict` — any non-standard JWT claims
- `user.auth_method: str` — "jwt" | "cookie" | "telegram"

## Token operations
```python
from forgeapi.auth import auth

access  = auth.token(user)
refresh = auth.refresh_token(user)
payload = auth.decode(token, expected_type="access")  # raises TokenExpiredError | TokenInvalidError

auth.set_cookie(response, {"sub": str(user.id)})  # cookie strategy
auth.delete_cookie(response)
```

## Login / Register endpoint pattern (JWT)
```python
@route.post("/login")
async def login(self, payload: LoginPayload) -> dict:
    user = await User.get_or_none(email=payload.email)
    if not user or not user.verify_password(payload.password):
        raise HTTPException(401, "Invalid credentials")
    access  = auth.token(user)
    refresh = auth.refresh_token(user)
    return {"access_token": access, "refresh_token": refresh, "token_type": "bearer"}

@route.post("/refresh")
async def refresh(self, payload: RefreshPayload) -> dict:
    try:
        data = auth.decode(payload.refresh_token, expected_type="refresh")
    except (TokenExpiredError, TokenInvalidError) as e:
        raise HTTPException(401, str(e))
    user = await User.find_or_fail(int(data["sub"]))
    return {"access_token": auth.token(user), "token_type": "bearer"}
```

## Exceptions
- `forgeapi.exceptions.TokenExpiredError`
- `forgeapi.exceptions.TokenInvalidError`
- `forgeapi.exceptions.ForgeAPIConfigError`
""",

"permissions": """\
# forge-kits: Permissions (Spatie-style RBAC)

## Model setup
```python
from forgeapi.permissions import PermissionsMixin

class User(PermissionsMixin):
    id        = fields.IntField(primary_key=True)
    email     = fields.CharField(max_length=255, unique=True)
    is_active = fields.BooleanField(default=True)

    class Meta:
        table = "users"
```

Add `"forgeapi.permissions.models"` to Tortoise `apps` config, then run migrations.

## Route-level dependency injection
```python
from forgeapi.permissions import require_permission, require_role

@route.delete("/{id}")
async def destroy(self, id: int, user=require_permission("delete:posts")): ...

@route.get("/admin/stats")
async def stats(self, user=require_role("admin")): ...

# OR logic — user must have at least one
@route.post("/")
async def create(self, payload: PostCreate, user=require_permission("create:posts", "admin")): ...
```

## Instance-level checks
```python
await user.can("edit:posts")
await user.has_role("admin")
await user.has_all_permissions("edit:posts", "publish:posts")
await user.has_all_roles("admin", "moderator")
await user.get_all_permissions()  # list[str], cached
await user.get_role_names()       # list[str]
```

## Granting / revoking
```python
await user.give_permission("edit:posts")
await user.assign_role("editor")
await user.revoke_permission("delete:posts")
await user.remove_role("editor")
```

## DB tables created
- `permissions` (id, name, guard)
- `roles` (id, name, guard)
- `role_permissions` (M2M through table)
- `model_has_roles` (model_type, model_id, role_id)
- `model_has_permissions` (model_type, model_id, permission_id)
""",

"policies": """\
# forge-kits: Policies (Gate system)

## Policy class
```python
from forgeapi import Policy, gate

@gate.policy(Post)
class PostPolicy(Policy):
    async def before(self, user, action: str):
        if await user.has_role("admin"):
            return True   # admin bypasses all checks
        return None       # None = continue to action method

    async def view(self, user, post: Post) -> bool:
        return post.is_published or user.id == post.author_id

    async def update(self, user, post: Post) -> bool:
        return user.id == post.author_id

    async def delete(self, user, post: Post) -> bool:
        return user.id == post.author_id
```

## Gate closures (lightweight — no Policy class needed)
```python
gate.define("edit-post", lambda user, post: user.id == post.author_id)
gate.define("is-admin", lambda user: user.is_admin)
```

## Using in controllers
```python
from forgeapi import gate

@route.patch("/{id}")
async def update(self, id: int, payload: PostUpdatePayload, user: CurrentUser):
    post = await Post.find_or_fail(id)
    await gate.authorize(user, "update", post)   # raises 403 if denied
    return await post.update_from(payload)

# Check without raising:
if await gate.allows(user, "delete", post): ...
if await gate.denies(user, "update", post): ...
```

## Auto-discovery
```python
gate.discover("app/policies")  # imports all *_policy.py files
```

## Policy method naming
Methods map to action strings: `"view"` → `view(user, subject)`, `"update"` → `update(user, subject)`.
""",

"cache": """\
# forge-kits: Cache

## Import
```python
from forgeapi import Cache
```

## Basic operations
```python
await Cache.set("key", value, ttl=60)   # store for 60 seconds
await Cache.get("key")                   # → value or None
await Cache.get("key", default="x")     # → value or "x"
await Cache.has("key")                  # → bool
await Cache.forget("key")               # delete → bool
await Cache.flush()                     # clear all
```

## Common patterns
```python
# Get or compute
posts = await Cache.remember("posts:all", fn=lambda: fetch_posts(), ttl=300)

# Get and delete (one-time token)
token = await Cache.pull("reset:token:user42")

# Store forever (no TTL)
await Cache.forever("settings:global", config)

# Counters
await Cache.increment("views:post:1")       # → int
await Cache.decrement("stock:item:5")       # → int
await Cache.increment("counter", amount=5)
```

## forgeapi.toml
```toml
[cache]
driver    = "memory"   # "memory" | "redis"
prefix    = "myapp:"
ttl       = 3600       # default TTL in seconds (null = no expiry)

# Redis driver:
[cache]
driver    = "redis"
redis_url = "redis://localhost:6379/1"
prefix    = "myapp:"
```

## Drivers
- **memory** — in-process dict with TTL, no dependencies, resets on restart
- **redis** — persistent, shared across workers; requires `pip install forge-kits[redis]`

Core auto-configures Cache from forgeapi.toml on startup.
""",

"support": """\
# forge-kits: Support helpers

```python
from forgeapi import Number, Str, Time
```

## Number
```python
Number.format(1234567.89)           # "1,234,567.89"
Number.format(1234.5, decimals=0)   # "1,235"
Number.currency(99.9)               # "99.90"
Number.currency(100.00044443)       # "100.00"  (messy float → clean)
Number.file_size(1024)              # "1.0 KB"
Number.file_size(1048576)           # "1.0 MB"
Number.file_size(1024, unit="MB")   # "0.0 MB"  (forced unit)
Number.percent(0.754)               # "75.4%"
Number.abbreviate(1500000)          # "1.5M"
Number.abbreviate(2300)             # "2.3K"
Number.clamp(150, 0, 100)           # 100
```

## Str
```python
Str.limit("Hello world", 5)         # "Hello..."
Str.limit("Hello world", 5, " →")  # "Hello →"
Str.slug("Hello World!")            # "hello-world"
Str.random(16)                      # "Xk9mR2pLqT8vNcYw"
Str.random(8, alphabet="0123456789")
Str.title("hello world")            # "Hello World"
Str.snake("HelloWorld")             # "hello_world"
Str.camel("hello_world")            # "helloWorld"
Str.pascal("hello_world")           # "HelloWorld"
Str.truncate_words("a b c d", 2)    # "a b..."
Str.strip_tags("<b>Hello</b>")      # "Hello"
Str.mask("1234567890", start=4)     # "1234******"
Str.contains("Hello", "ell")        # True
```

## Time
```python
Time.now()                          # datetime UTC
Time.now("Europe/Kyiv")             # datetime in TZ
Time.parse("2025-07-14")            # → datetime
Time.format(dt, "%d/%m/%Y")         # "14/07/2025"
Time.to_timezone(dt, "US/Eastern")  # convert TZ
Time.timestamp(dt)                  # Unix int
Time.add(dt, days=1, hours=3)       # → datetime
Time.subtract(dt, days=7)           # → datetime
Time.diff_in_days(dt1, dt2)         # int
Time.human(dt)                      # "5 minutes ago" / "in 3 hours"
Time.is_past(dt)                    # bool
Time.is_future(dt)                  # bool
Time.start_of_day(dt)               # 00:00:00
Time.end_of_day(dt)                 # 23:59:59
```
""",

"pagination": """\
# forge-kits: Pagination

## Two approaches

### 1. Paginator DI (classic)
```python
from forgeapi.pagination import Pagination

@route.get("/")
async def index(self, pagination: Pagination) -> dict:
    total = await Post.all().count()
    items = await Post.all().offset(pagination.offset).limit(pagination.limit)
    return {"items": items, "total": total, "page": pagination.page}
```

### 2. QuerySet .paginate() (recommended)
```python
@route.get("/", response_model=None)
async def index(self, request: Request):
    return await Post.all().order_by("-created_at").paginate(request, PostResponse)
```
Returns `PaginatedResponse` with `data`, `meta` (page/per_page/total/last_page), `links` (prev/next).

Query params: `?page=2&per_page=50`

## Global configuration
```python
Core(app, pagination=20)   # sets default_limit=20
```
```toml
[pagination]
default_limit = 20
max_limit     = 100
```
""",

"schemas": """\
# forge-kits: Schemas (Pydantic)

```python
from forgeapi import BaseSchema, BaseCreateSchema, BaseUpdateSchema
```

## BaseSchema — response / read
```python
class PostResponse(BaseSchema):
    # Inherits: id, created_at, updated_at — model_config from_attributes=True
    title: str
    body: str
    author_id: int

response = PostResponse.model_validate(orm_post_instance)
```

## BaseCreateSchema — POST body
```python
class PostCreatePayload(BaseCreateSchema):
    title: str
    body: str
    tags: list[str] = []
```

## BaseUpdateSchema — PATCH body
```python
class PostUpdatePayload(BaseUpdateSchema):
    # ALL fields must be Optional — raises TypeError otherwise
    title: str | None = None
    body: str | None = None
```

## generate:schema CLI
```bash
forgeapi generate:schema Post --payload        # Create + Update payloads
forgeapi generate:schema Post --response       # PostResponse
forgeapi generate:schema Post --payload --response  # all three
```
""",

"middleware": """\
# forge-kits: Middleware & Guards

## Built-in middleware (via Core)
- `access_log=True` — logs method, path, status, duration
- `request_id=True` — injects `X-Request-ID` header
- `cors=["*"]` — CORSMiddleware
- `rate_limit=60` — IP-based rate limit (req/min)

## Custom middleware
```python
from forgeapi.middleware import Middleware

class TimingMiddleware(Middleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        import time
        start = time.monotonic()
        response = await call_next(request)
        response.headers["X-Process-Time"] = str(time.monotonic() - start)
        return response

core.use(TimingMiddleware)
```

## Guard — per-route / per-controller
```python
from forgeapi.middleware import Guard

class ApiKeyGuard(Guard):
    async def handle(self, request: Request) -> None:
        if not request.headers.get("X-API-Key"):
            raise HTTPException(403, "Missing API key")

# Per-route:
@route.delete("/{id}", dependencies=[Depends(ApiKeyGuard())])
async def destroy(self, id: int): ...

# Per-controller:
class AdminController(Controller):
    guards = [ApiKeyGuard()]
```
""",

"cli": """\
# forge-kits: CLI Reference

Entry point: `forgeapi`

## Project scaffolding
```bash
forgeapi init <project-name>
```

## Code generation
```bash
forgeapi make:controller <Name>
forgeapi make:model <Name>
forgeapi make:event <Name>
forgeapi make:listener <Name>
forgeapi make:seed <Name>
forgeapi generate:schema Post --payload --response
```

## DB commands (NEVER use aerich directly)
```bash
forgeapi db:init
forgeapi db:makemigrations [-n <name>]
forgeapi db:migrate
forgeapi db:downgrade
forgeapi db:history
forgeapi db:seed
forgeapi db:fresh
```

## Inspection
```bash
forgeapi routers    # list all routes
forgeapi models     # list all models
```

## Dev server (NEVER use uvicorn directly)
```bash
forgeapi runserver
forgeapi runserver --port 9000 --host 0.0.0.0 --reload
```
""",

"config": """\
# forge-kits: Configuration (forgeapi.toml)

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
strategy           = "jwt"
jwt_secret_env     = "JWT_SECRET"
access_ttl_minutes = 30
refresh_ttl_days   = 7

[pagination]
default_limit = 20
max_limit     = 100

[cache]
driver    = "memory"   # or "redis"
prefix    = ""
redis_url = "redis://localhost:6379/0"
```

## Loading in code
```python
from forgeapi import load_config, KitConfig

cfg: KitConfig = load_config()
cfg.project.name
cfg.auth.strategy
cfg.pagination.default_limit
cfg.cache.driver
```
""",

"models": """\
# forge-kits: Tortoise ORM Models + ModelMixin

## ModelMixin shortcuts
```python
from forgeapi import ModelMixin
from tortoise import fields, Model

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
```

## ModelMixin API
```python
post = await Post.find_or_fail(id)            # 404 if not found
post = await Post.create_from(payload, author_id=user.id)
post = await post.update_from(payload)

# QuerySet + .paginate()
await Post.filter(is_published=True).paginate(request, PostResponse)
await Post.published().order_by("-created_at").paginate(request, PostResponse)
```

## All field types
```python
fields.IntField(pk=True)
fields.BigIntField()
fields.CharField(max_length=255)
fields.TextField()
fields.FloatField()
fields.DecimalField(max_digits=10, decimal_places=2)
fields.BooleanField(default=False)
fields.DatetimeField(auto_now_add=True)
fields.DateField()
fields.JSONField(default=dict)
fields.UUIDField()
fields.ForeignKeyField("models.User", related_name="posts", on_delete=fields.CASCADE)
fields.ManyToManyField("models.Tag", related_name="posts")
```

## Meta options
```python
class Meta:
    table = "posts"
    ordering = ["-created_at"]
    unique_together = [("author_id", "slug")]
```
""",

"tortoise": """\
# forge-kits: Tortoise ORM — Basic queries

## CRUD
```python
post = await Post.create(**payload.model_dump(), author_id=int(user.id))
post, created = await Post.get_or_create(slug="x", defaults={"title": "X"})
post = await Post.get(id=1)          # raises DoesNotExist
post = await Post.get_or_none(id=1) # None if missing
post.title = "New"; await post.save()
await post.update_from_dict(payload.model_dump(exclude_none=True)).save()
await post.delete()
```

## Filter / order / paginate
```python
posts  = await Post.filter(is_active=True).order_by("-created_at").offset(0).limit(20)
total  = await Post.all().count()
exists = await Post.filter(slug="x").exists()
await Post.filter(author_id=1).update(is_active=False)
await Post.filter(author_id=1).delete()
```

## Lookup suffixes
```python
Post.filter(title__icontains="hello")
Post.filter(created_at__gte=dt)
Post.filter(id__in=[1, 2, 3])
Post.filter(author_id__isnull=False)
Post.exclude(is_active=False)
```

## Async gather (parallel queries)
```python
import asyncio
total, items = await asyncio.gather(
    Post.filter(is_active=True).count(),
    Post.filter(is_active=True).order_by("-created_at").offset(0).limit(20),
)
```
""",

"tortoise_advanced": """\
# forge-kits: Tortoise ORM — Advanced queries

## Q objects (OR / NOT)
```python
from tortoise.expressions import Q
Post.filter(Q(title__icontains="py") | Q(body__icontains="py"))
Post.filter(~Q(is_active=False))
```

## Prefetch relations (avoids N+1)
```python
posts = await Post.all().prefetch_related("author", "tags")
posts = await Post.all().select_related("author")
posts = await Post.all().prefetch_related("author__profile")
```

## values / values_list
```python
rows = await Post.filter(is_active=True).values("id", "title")
ids  = await Post.all().values_list("id", flat=True)
```

## Aggregations
```python
from tortoise.functions import Count, Sum, Max, Avg
result = await Post.annotate(n=Count("id")).group_by("author_id").values("author_id", "n")
```

## Bulk create
```python
posts = [Post(title=f"Post {i}", author_id=1) for i in range(100)]
await Post.bulk_create(posts, batch_size=50)
```

## Transactions
```python
from tortoise import transactions

async with transactions.in_transaction():
    user = await User.create(email="alice@example.com")
    await Profile.create(user_id=user.id)

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


def get_docs(topic: str) -> str:
    """Return inline API documentation for a forge-kits topic.

    IMPORTANT: Call get_docs('workflow') FIRST when starting any forge-kits project
    or task — it contains critical rules about which CLI commands to use and which
    to avoid (e.g. never use uvicorn or aerich directly).

    Start with 'cheatsheet' — covers 80% of tasks in ~200 tokens.
    Only call specific topics when you need more detail.

    Topics (lightest → heaviest):
      cheatsheet, workflow, pagination, config, schemas, middleware,
      core, cli, auth, permissions, policies, cache, support,
      controllers, events, tortoise, tortoise_advanced, models

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
