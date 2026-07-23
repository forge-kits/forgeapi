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

## Schemas | Auth | Broadcasting
```python
class PostResponse(BaseSchema): title: str          # + id/created_at/updated_at inherited
class PostCreate(BaseCreateSchema): title: str
class PostUpdate(BaseUpdateSchema): title: str | None = None  # auto-optional

user: CurrentUser   # 401 if missing  |  user: OptionalUser  # None if missing
access = auth.token(user)

# app/events/__init__.py
from forgeapi import BroadcastManager
broadcast = BroadcastManager(driver="redis", url="redis://localhost:6379",
                              namespace="myapp", mode="stream", maxlen=1000)

# app/listeners/order_listener.py
@broadcast.on("order:created")
async def handle_order(data: dict) -> None: ...

# emit from controller:
await broadcast.emit("order:created", {"order_id": 1})
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

## Storage | ImageProcessor
```python
from forgeapi import Storage, ImageProcessor
path = await Storage.put("files/doc.pdf", data)
data = await Storage.get("files/doc.pdf")   # bytes | None
url  = Storage.url("files/doc.pdf")
# Image upload + resize
path = await (await ImageProcessor.from_upload(file)).resize(256, 256, crop=True).store("avatars/1", extension="webp")
```

## Scheduler (schedule.py)
```python
# schedule.py — define in project root
from forgeapi import Scheduler
scheduler = Scheduler()
scheduler.call(cleanup).every(30).name("cleanup")       # every 30 min
scheduler.call(report).daily_at("09:00").name("report")
scheduler.call(backup).weekly_on("sunday", at="03:00").name("backup")
# forgeapi schedule:work   — dev loop
# forgeapi schedule:run    — run due tasks once (cron)
# forgeapi schedule:list   — show all tasks + DB state
# in lifespan: task = asyncio.create_task(scheduler.run())
```

## Query Scopes | Observers
```python
from forgeapi.database import scope, ModelObserver
class Post(ModelMixin, Model):       # ALWAYS inherit both ModelMixin AND Model
    @scope
    def published(qs): return qs.filter(is_published=True)

posts = await Post.all().published().order_by("-created_at")

class PostObserver(ModelObserver):
    async def saved(self, instance, **kw): await Cache.forget(f"post:{instance.id}")
Post.observe(PostObserver)
```

## CLI
```bash
forgeapi make:controller Post && forgeapi make:model Post
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
| Run scheduled tasks | `forgeapi schedule:work` (dev) / `forgeapi schedule:run` (cron) | calling scheduler directly |

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
forgeapi make:seed User               # database/seeds/user_seeder.py
forgeapi generate:schema Post --payload --response
```
""",

"core": """\
# forge-kits: Core (entry-point wiring)

Import: `from forgeapi import Core`

## Constructor

```python
Core(app: FastAPI, *, config: KitConfig | None = None)
```

**One argument.** Everything is config-driven — what runs depends on which
files exist in `config/`. `forgeapi.toml` is no longer supported.

## Minimal main.py

```python
from fastapi import FastAPI
from forgeapi import Core
from tortoise.contrib.fastapi import register_tortoise
from config.database import TORTOISE_ORM

app = FastAPI()
core = Core(app)   # all wiring from config/

register_tortoise(app, config=TORTOISE_ORM, generate_schemas=False, add_exception_handlers=True)
```

## What boots when

| Module | Activated by |
|---|---|
| Middleware | `config/http.py` — cors, rate_limit, request_id, access_log |
| Auth guards | `config/auth.py` exists |
| Storage | `config/storage.py` exists |
| Controllers | `controllers_dir` exists — all `*_controller.py` auto-imported |
| Event listeners | `listeners_dir` exists |
| Policies | `policies_dir` exists |
| Permissions | any model inherits `PermissionsMixin` — auto-detected |
| Telescope | `"debug": True` in `config/project.py` |
| Pagination, Cache | always configured (defaults or from their sections) |
| Custom providers | `"providers"` list in `config/project.py` |

## config/ directory

Each `config/<section>.py` defines `config = {...}`. Section name = filename.
All sections are optional. Unknown sections become custom config accessible via
`core.config.get("section.key")`.

```python
# config/project.py
from forgeapi import env
config = {"name": "My App", "debug": env("APP_DEBUG", False), "providers": []}

# config/http.py
config = {"cors": ["*"], "rate_limit": 60, "request_id": True, "access_log": True}

# config/auth.py
config = {"default": "api", "guards": {
    "api": {"strategy": "cookie", "secret": env("COOKIE_SECRET")}
}}

# config/storage.py
config = {"driver": "local", "root": "storage/app", "base_url": "/storage"}

# config/database.py — TORTOISE_ORM lives here (no config dict needed)
TORTOISE_ORM = {"connections": {...}, "apps": {...}}
```

## Custom providers

```python
from forgeapi import Provider

class MetricsProvider(Provider):
    def register(self) -> None: ...   # wiring — no user imports here
    def boot(self) -> None: ...       # discovery — runs after all register()s
```

Register in `config/project.py`: `config = {"providers": [MetricsProvider]}`

## Post-setup API

```python
core.auth       # Auth facade | None (None when config/auth.py absent)
core.config     # KitConfig — access any section
core.providers  # list of active Provider instances
core.use(MiddlewareClass, **kwargs)          # add middleware after boot
core.include_router(router, prefix="/")     # prepends base_prefix
```

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
# forge-kits: BroadcastManager

## Setup
```python
from forgeapi import BroadcastManager

broadcast = BroadcastManager(
    driver="redis",
    url="redis://localhost:6379",
    namespace="shop",
    mode="stream",   # "pubsub" | "stream"
    maxlen=1000,     # stream only: keep last N messages
)
```

## Register handler
```python
@broadcast.on("order:created")
async def handle(data: dict) -> None:
    await notify(data["id"])
```

## Emit
```python
await broadcast.emit("order:created", {"id": 42, "total": 99.0})
```

## Lifespan (stream)
```python
@asynccontextmanager
async def lifespan(app):
    await broadcast.connect(group="backend", consumer="worker-1")
    yield
    await broadcast.disconnect()
```

## Lifespan (pubsub)
```python
@asynccontextmanager
async def lifespan(app):
    await broadcast.connect()
    yield
    await broadcast.disconnect()
```

## Mode comparison
| | pubsub | stream |
|---|---|---|
| Persistence | No | Yes (Redis Streams) |
| Offline workers | Miss messages | Catch up on reconnect |
| Consumer groups | No | Yes — each group gets all messages |
| Horizontal scaling | No | Yes — consumers share load within group |

## Cross-project
Both projects use same `namespace`, handlers receive plain `dict` — no shared classes needed.
""",

"auth": """\
# forge-kits: Authentication

## Quick setup via Core
```python
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
- `user.id: str` — session `sub` claim; use `int(user.id)` for DB queries
- `user.username: str | None`
- `user.extra: dict` — any non-standard session claims
- `user.auth_method: str` — "cookie" | "telegram"

## Session operations
```python
from forgeapi.auth import auth

token = auth.token(user)  # returns signed session value

auth.set_cookie(response, {"sub": str(user.id)})  # write session cookie
auth.delete_cookie(response)                        # clear session cookie
```

## Login / Register endpoint pattern (cookie)
```python
@route.post("/login")
async def login(self, payload: LoginPayload, response: Response) -> dict:
    user = await User.get_or_none(email=payload.email)
    if not user or not user.verify_password(payload.password):
        raise HTTPException(401, "Invalid credentials")
    auth.set_cookie(response, {"sub": str(user.id), "username": user.username})
    return {"message": "Logged in"}

@route.post("/logout")
async def logout(self, response: Response) -> dict:
    auth.delete_cookie(response)
    return {"message": "Logged out"}
```

## Exceptions
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

## Scheduler
```bash
forgeapi schedule:run             # run due tasks once (use from cron)
forgeapi schedule:run <name>      # run specific task manually
forgeapi schedule:work            # infinite dev loop
forgeapi schedule:list            # show all tasks + DB state
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
listeners_dir   = "app/listeners"
seeds_dir       = "database/seeds"
base_prefix     = "/api/v1"

[auth]
strategy = "cookie"

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

"storage": """\
# forge-kits: Storage

Import: `from forgeapi import Storage`
Install extras: `pip install forge-kits[s3]` (S3) / `pip install forge-kits[images]` (Pillow)

## Configuration (config/storage.py)
```python
from forgeapi import env

config = {
    "driver": "local",        # "local" | "s3"
    "root": "storage/app",    # local: filesystem root
    "base_url": "/storage",   # local: public URL prefix
    # S3 / MinIO / Cloudflare R2:
    # "bucket": "my-bucket",
    # "region": "us-east-1",
    # "access_key": env("AWS_ACCESS_KEY_ID"),
    # "secret_key": env("AWS_SECRET_ACCESS_KEY"),
    # "endpoint_url": "",
}
```

## Basic operations
```python
path  = await Storage.put("avatars/user-1.jpg", image_bytes)   # → stored path
data  = await Storage.get("avatars/user-1.jpg")                 # → bytes | None
ok    = await Storage.exists("avatars/user-1.jpg")              # → bool
await Storage.delete("avatars/user-1.jpg")
files = await Storage.list("avatars/")                          # → list[str]
url   = Storage.url("avatars/user-1.jpg")                       # → "/storage/avatars/..."
```

## Multiple disks
```python
from forgeapi.storage import LocalDriver, S3Driver

Storage.add_disk("public", LocalDriver(root="public/", base_url="/public"))
Storage.add_disk("backups", S3Driver(bucket="my-backups", region="eu-central-1",
                                     access_key="...", secret_key="..."))

await Storage.disk("backups").put("dump.sql.gz", data)
url = Storage.disk("public").url("logo.png")
```

## ImageProcessor (Pillow)
```python
from forgeapi import ImageProcessor

# from bytes or FastAPI UploadFile
pipeline = ImageProcessor.process(raw_bytes)
pipeline = await ImageProcessor.from_upload(upload_file)

# transform (fluent, returns self)
pipeline.resize(800, 600)            # fit (preserves ratio)
pipeline.resize(800, 600, crop=True) # crop-fill to exact size
pipeline.thumbnail(256)              # shrink to 256px max side
pipeline.quality(85)                 # JPEG quality
pipeline.convert("WEBP")             # format conversion
pipeline.grayscale()                 # desaturate

# output
data: bytes = pipeline.to_bytes()

# store directly (returns stored path)
path = await pipeline.store("avatars/user-1", extension="webp")
path = await pipeline.store(directory="thumbs", extension="jpg")
path = await pipeline.store("hero.jpg", disk="public")
```

## Upload + resize pattern (controller)
```python
@route.post("/avatar", status_code=201)
async def upload_avatar(self, file: UploadFile, user: CurrentUser) -> dict:
    path = await (await ImageProcessor.from_upload(file)) \\
        .resize(256, 256, crop=True) \\
        .store(f"avatars/{user.id}", extension="webp")
    return {"url": Storage.url(path)}
```
""",

"scheduler": """\
# forge-kits: Scheduler (DB-backed)

State (next_run_at, last_run_at, status, errors) is persisted in the `jobs`
table via Tortoise. Jobs are defined in code; the DB tracks their lifecycle.

## Tortoise setup
Add `forgeapi.scheduling` to `config/database.py` models list:
```python
"models": ["database.models", "forgeapi.scheduling", "forgeapi.permissions.models"]
```
The CLI creates the table automatically with `generate_schemas(safe=True)`.

## schedule.py
Define all jobs in `schedule.py` at the project root (created by `forgeapi init`):
```python
from forgeapi import Scheduler

scheduler = Scheduler()

scheduler.call(send_report).daily_at("09:00").name("newsletter")
scheduler.call(cleanup).every(30).name("cleanup")          # every 30 min
scheduler.call(backup).weekly_on("sunday", at="03:00").name("backup")
scheduler.call(sync).hourly().name("sync-rates")
scheduler.call(ping).every_minute().name("health")
```

`.name("label")` sets the unique key in the DB and in CLI commands.

## Timing methods
| Method | When |
|---|---|
| `.every_minute()` | Every minute |
| `.every(n)` | Every n minutes |
| `.hourly()` | Every hour |
| `.every_hours(n)` | Every n hours |
| `.daily()` | Daily at midnight |
| `.daily_at("HH:MM")` | Daily at given time |
| `.weekly()` | Monday midnight |
| `.weekly_on("day", at="HH:MM")` | Named weekday at given time |

Days for weekly_on: monday, tuesday, wednesday, thursday, friday, saturday, sunday

Both sync and async callables are accepted.

## CLI commands
```bash
forgeapi schedule:work            # dev: infinite loop, sleeps until next job
forgeapi schedule:run             # cron: run all due tasks once
forgeapi schedule:run newsletter  # run a specific task by name immediately
forgeapi schedule:list            # show all tasks + next/last run + status
```

For production use a cron job calling `schedule:run` every minute:
```cron
* * * * * cd /app && forgeapi schedule:run >> /var/log/scheduler.log 2>&1
```

## FastAPI lifespan (in-process)
```python
import asyncio
from schedule import scheduler   # your schedule.py

@asynccontextmanager
async def lifespan(app):
    task = asyncio.create_task(scheduler.run())
    yield
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
```

`scheduler.run()` calls `sync()` on startup (upserts all jobs to DB), then
loops indefinitely — sleeping until the soonest task, then calling `run_due()`.

## ScheduledTask model fields
name, schedule_type, schedule_config, is_enabled, next_run_at, last_run_at,
last_status ("success"/"failed"), last_error. Table: `jobs`.
""",

"scopes": """\
# forge-kits: Query Scopes

Import: `from forgeapi.database import scope`

## Define
```python
from tortoise import Model, fields
from forgeapi import ModelMixin
from forgeapi.database import scope

class Post(ModelMixin, Model):
    is_published = fields.BooleanField(default=False)
    author_id    = fields.IntField()

    @scope
    def published(qs):
        return qs.filter(is_published=True)

    @scope
    def by_author(qs, author_id: int):
        return qs.filter(author_id=author_id)
```

IMPORTANT: `@scope` functions receive the queryset as first arg (not `cls`/`self`).
The model must inherit both `ModelMixin` AND `Model` — `class Post(ModelMixin, Model)`.

## Use
```python
# class-level call → fresh queryset
posts = await Post.published()
posts = await Post.by_author(42)

# chain on any queryset
posts = await Post.all().published().by_author(42).order_by("-created_at").limit(20)
posts = await Post.filter(is_active=True).published()
```

## How it works
`@scope` registers the function in `model._scopes`. `ForgeQuerySet.__getattr__`
looks it up and injects the queryset as the first argument. Works through
inheritance — subclass scopes are found via `__mro__` traversal.
""",

"observers": """\
# forge-kits: Model Observers

Import: `from forgeapi.database import ModelObserver`

## Define
```python
from forgeapi.database import ModelObserver

class PostObserver(ModelObserver):
    async def creating(self, instance, **kw): ...   # before first save
    async def created(self, instance, **kw): ...    # after first save
    async def updating(self, instance, **kw): ...   # before update save
    async def updated(self, instance, **kw): ...    # after update save
    async def saving(self, instance, **kw): ...     # before any save (create OR update)
    async def saved(self, instance, **kw): ...      # after any save
    async def deleting(self, instance, **kw): ...   # before delete
    async def deleted(self, instance, **kw): ...    # after delete
```

Override only the hooks you need. All methods are optional.

## Register
```python
# class — auto-instantiated
Post.observe(PostObserver)

# instance
Post.observe(PostObserver())
```

Register at startup — before first request (e.g. in main.py or a Provider's `boot()`).

## Cache invalidation example
```python
from forgeapi import Cache
from forgeapi.database import ModelObserver

class PostObserver(ModelObserver):
    async def saved(self, instance, **kw):
        await Cache.forget(f"post:{instance.id}")
        await Cache.forget("posts:index")

    async def deleted(self, instance, **kw):
        await Cache.forget(f"post:{instance.id}")

Post.observe(PostObserver)
```

## Audit log example
```python
class PostObserver(ModelObserver):
    async def created(self, instance, **kw):
        await AuditLog.create(model="Post", action="created", record_id=instance.id)

    async def deleted(self, instance, **kw):
        await AuditLog.create(model="Post", action="deleted", record_id=instance.id)
```

## How it works
Uses Tortoise ORM signals (`pre_save`, `post_save`, `pre_delete`, `post_delete`).
`creating`/`updating` are derived from `pre_save` using `instance._saved_in_db`.
Partial observers (only some hooks defined) are handled — only relevant signals
are registered.
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
      core, cli, auth, permissions, policies, cache, storage, scheduler,
      scopes, observers, support, controllers, events, tortoise, tortoise_advanced, models

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
