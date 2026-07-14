# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

**forge-kits** (`import forgeapi`) — a FastAPI toolkit that adds controllers, events, permissions, auth, cache, and CLI scaffolding on top of FastAPI. All features are optional and wired together via the `Core` class.

Published to PyPI as `forge-kits`. Requires Python 3.11+.

## MCP Server

forge-kits ships an MCP server so Claude can look up API docs and generate boilerplate without reading source files.

**Install:**
```bash
pip install forge-kits[mcp]
```

**Quick setup (recommended):**
```bash
claude mcp add forge-kits forgeapi-mcp              # per-project (.mcp.json)
claude mcp add forge-kits forgeapi-mcp --scope global  # global (~/.claude/settings.json)
```

**Or manually add to `.mcp.json` in the project root:**
```json
{
  "mcpServers": {
    "forge-kits": {
      "command": "forgeapi-mcp"
    }
  }
}
```

**Source:** split across `forgeapi/mcp/` — `server.py` (entry point), `docs.py`, `examples.py`, `generators.py`, `scanner.py`.

**Available tools:**
- `get_docs(topic)` — API reference for: `cheatsheet`, `workflow`, `core`, `controllers`, `events`, `auth`, `permissions`, `policies`, `pagination`, `schemas`, `middleware`, `cli`, `config`, `models`, `cache`, `support`, `tortoise`, `tortoise_advanced`
- `get_example(pattern)` — Complete working code for: `crud_controller`, `redis_event`, `stream_event`, `jwt_auth`, `rbac`, `pagination`, `guard`, `cache`
- `generate_controller(name, routes)` — Generate a Controller class
- `generate_event(name, fields)` — Generate an Event class + listener
- `generate_schema(name, fields, mode)` — Generate Pydantic schemas
- `scan_project(path)` — Deep AST scan: models, controllers, schemas, events, listeners, seeders, deps, .env keys
- `project_info(path)` — Read `forgeapi.toml` and list project files

## Commands

```bash
# Install in editable mode
pip install -e .

# Run all tests
pytest

# Run a single test file
pytest tests/test_events.py

# Run a single test
pytest tests/test_events.py::test_name

# CLI
forgeapi --help
forgeapi init my-project
forgeapi make:controller Post
forgeapi make:model Post
forgeapi make:event UserRegistered
forgeapi generate:schema User --payload --response --crud
forgeapi db:migrate
forgeapi db:seed
forgeapi routers
```

Tests use `asyncio_mode = "auto"` (configured in `pyproject.toml`) — no need to mark tests with `@pytest.mark.asyncio`.

## Architecture

### Entry point: `Core` (forgeapi/kit.py)

`Core` is the main wiring class. It accepts a FastAPI `app` and optional feature flags:

```python
Core(
    app,
    auth=True,          # JWT / Cookie / Telegram (from forgeapi.toml)
    cors=["*"],
    rate_limit=60,      # req/min per IP
    pagination=20,      # default page size
    events=True,        # auto-load listeners
    permissions=True,   # auto-detect PermissionsMixin model
    controllers=True,   # auto-discover *_controller.py
    debug=False,        # enables Telescope (never in production)
)
```

On startup `Core`:
1. Loads `forgeapi.toml` via `KitConfig` (Pydantic models, all fields optional)
2. Registers middleware in stack order
3. Auto-discovers controllers via `**/*_controller.py` glob
4. Auto-loads event listeners from `listeners_dir`
5. Auto-detects the model that inherits `PermissionsMixin`
6. Configures `Cache` from `[cache]` section

### Controllers (forgeapi/controllers/base.py)

Route classes that auto-register with FastAPI. CamelCase name → URL prefix:
- `PostController` → `/posts`
- `AdminUserController` → `/admin/users`

```python
class PostController(Controller):
    prefix = "/posts"        # optional override
    tags   = ["posts"]
    schema = PostResponse    # auto response_model on all routes (skips status_code=204 and explicit response_model=None)
    guards = [SomeGuard()]

    @route.get("/", response_model=None)   # override: paginated envelope
    async def index(self, request: Request):
        return await Post.all().order_by("-created_at").paginate(request, PostResponse)

    @route.post("/", status_code=201)
    async def create(self, payload: PostCreatePayload, user: CurrentUser): ...

    @route.delete("/{id}", status_code=204)
    async def destroy(self, id: int): ...
```

`@route` mirrors FastAPI's decorators (`get`, `post`, `put`, `patch`, `delete`).

### ModelMixin (forgeapi/database/model.py)

Inherit alongside `tortoise.Model` to get shortcuts and `.paginate()` on every QuerySet:

```python
from forgeapi import ModelMixin
from tortoise import fields, Model

class Post(ModelMixin, Model):
    ...
```

**API:**
```python
post  = await Post.find_or_fail(id)                     # 404 if not found
post  = await Post.create_from(payload, author_id=1)    # create from Pydantic schema
post  = await post.update_from(payload)                 # partial update from schema
posts = await Post.all().paginate(request, PostResponse) # → PaginatedResponse
```

`ModelMixin.__init_subclass__` automatically injects `ForgeManager` so `.paginate()` is available on every QuerySet chain (`Post.filter(...).paginate(...)`).

### Events (forgeapi/events/)

Three transport modes controlled by class vars:

| `redis` | `redis_type` | Behaviour |
|---------|-------------|-----------|
| `False` | — | In-process dispatch |
| `True` | `"pubsub"` (default) | Redis pub/sub — fan-out to all workers, optional `ttl` for dedup |
| `True` | `"stream"` | Redis Streams — persistent, consumer groups, `namespace` sets stream key prefix |

```python
class OrderCreated(Event):
    background = True   # fire-and-forget
    redis = True
    ttl = 60            # dedup: only 1st worker processes within 60s

@listen(OrderCreated)
async def notify(event: OrderCreated): ...

await OrderCreated(order_id=42).dispatch()
```

`EventBus` is a singleton. In tests always call `EventBus.reset()` before and after each test.

**RedisBus** (`forgeapi/events/redis_bus.py`) — bridges events across separate projects (different EventBus instances) over a shared Redis channel.

### Permissions (forgeapi/permissions/)

Spatie-style polymorphic RBAC. The user model inherits `PermissionsMixin` — no extra columns on the model itself. All assignments live in shared pivot tables (`model_has_roles`, `model_has_permissions`).

```python
await user.give_permission("edit:posts")
await user.assign_role("admin")
await user.can("edit:posts")     # → bool
await user.has_role("admin")     # → bool

@route.delete("/{id}")
async def destroy(self, id: int, user=require_permission("delete:posts")): ...
```

`setup_permissions(UserModel)` must be called before queries. `Core(permissions=True)` does this automatically when it detects a `PermissionsMixin` subclass.

### Policies (forgeapi/policies/)

Laravel-style Policy + Gate system for model-level authorization.

```python
from forgeapi import Policy, gate

@gate.policy(Post)
class PostPolicy(Policy):
    async def before(self, user, action: str):
        if await user.has_role("admin"):
            return True   # admin bypasses all checks
        return None       # continue to action method

    async def update(self, user, post: Post) -> bool:
        return user.id == post.author_id

    async def delete(self, user, post: Post) -> bool:
        return user.id == post.author_id
```

**Using in controllers:**
```python
await gate.authorize(user, "update", post)   # raises HTTP 403 if denied
await gate.allows(user, "delete", post)      # → bool
await gate.denies(user, "update", post)      # → bool
```

`gate` is a module-level singleton. `gate.discover("app/policies")` auto-imports all `*_policy.py` files.

### Auth (forgeapi/auth/)

Three strategies, selected via `forgeapi.toml` `[auth] strategy`:

- **jwt** — `Authorization: Bearer <token>` header, uses `JWT_SECRET` env var
- **cookie** — HMAC-SHA256 signed JSON in HttpOnly cookie
- **telegram** — validates `initData` from Telegram Mini App

```python
from forgeapi.auth import CurrentUser, OptionalUser, auth

@route.get("/me")
async def me(user: CurrentUser): ...      # 401 if missing

@route.get("/feed")
async def feed(user: OptionalUser): ...   # None if missing

access  = auth.token(user)           # access token (takes DB model instance)
refresh = auth.refresh_token(user)   # refresh token (JWT only)
payload = auth.decode(token, expected_type="access")  # verify + decode

# Cookie strategy only:
auth.set_cookie(response, {"sub": str(user.id), "username": user.username})
auth.delete_cookie(response)
```

### Cache (forgeapi/cache/)

Async key-value cache with memory (default) and Redis drivers. Configured automatically by `Core` from `forgeapi.toml`.

```python
from forgeapi import Cache

await Cache.set("key", value, ttl=60)
await Cache.get("key", default=None)
await Cache.remember("posts:all", fn=fetch_posts, ttl=300)  # get or compute
await Cache.pull("reset:token:42")   # get and delete
await Cache.forever("settings", cfg)
await Cache.increment("views:post:1")
await Cache.forget("key")
await Cache.flush()
```

Two drivers: `memory` (in-process, resets on restart) and `redis` (persistent, shared across workers — requires `pip install forge-kits[redis]`).

### Support (forgeapi/support/)

Utility helpers for formatting and string/time manipulation.

```python
from forgeapi import Number, Str, Time

Number.format(1234567.89)        # "1,234,567.89"
Number.currency(99.9)            # "99.90"
Number.file_size(1048576)        # "1.0 MB"
Number.percent(0.754)            # "75.4%"
Number.abbreviate(1_500_000)     # "1.5M"

Str.limit("Hello world", 5)      # "Hello..."
Str.slug("Hello World!")         # "hello-world"
Str.random(16)                   # cryptographically random string
Str.snake("HelloWorld")          # "hello_world"
Str.mask("1234567890", start=4)  # "1234******"

Time.now("Europe/Kyiv")          # datetime in TZ
Time.human(dt)                   # "5 minutes ago" / "in 3 hours"
Time.add(dt, days=1, hours=3)
Time.to_timezone(dt, "US/Eastern")
Time.format(dt, "%d/%m/%Y")
```

### Schemas (forgeapi/schemas/base.py)

Three base classes: `BaseSchema` (read/response, `from_attributes=True`), `BaseCreateSchema`, `BaseUpdateSchema`. All fields in `BaseUpdateSchema` are optional by default.

### Middleware (forgeapi/middleware/)

Custom middleware inherits `Middleware` (abstract, Starlette-compatible). Per-controller/per-route access control uses `Guard` abstract base — guards receive the request and raise `HTTPException` to block.

### Telescope (forgeapi/telescope/)

Debug-only request inspector activated by `Core(debug=True)`. Captures SQL queries, logs, events, and custom jobs per request in a 200-entry circular buffer. Accessible via WebSocket at `ws://host/_forge/telescope/ws`. Never enable in production — it patches global logging and ORM internals.

```python
from forgeapi.telescope import record_job
record_job("SendEmail", status="done", duration_ms=45.2)
```

### Configuration (forgeapi/config.py)

`forgeapi.toml` in the project root. All sections are optional:

```toml
[project]
name = "my-app"

[structure]
models_dir = "database/models"
controllers_dir = "app/controllers"
base_prefix = "/api/v1"

[auth]
strategy = "jwt"          # jwt | cookie | telegram
jwt_secret_env = "JWT_SECRET"

[pagination]
default_limit = 20
max_limit = 100

[cache]
driver    = "memory"      # memory | redis
prefix    = ""
ttl       = 3600          # default TTL in seconds (null = no expiry)
redis_url = "redis://localhost:6379/0"
```

### CLI (forgeapi/cli/)

Built with Typer + Rich. Code generation uses Jinja2 templates in `forgeapi/cli/templates/`. `forgeapi init` scaffolds a full project with Tortoise ORM, auth, and a sample controller.

## Key Files

| File | Purpose |
|------|---------|
| `forgeapi/kit.py` | `Core` class — main wiring |
| `forgeapi/config.py` | `KitConfig` — TOML config model |
| `forgeapi/controllers/base.py` | `Controller` + `@route` |
| `forgeapi/database/model.py` | `ModelMixin` — find_or_fail, create_from, update_from |
| `forgeapi/database/queryset.py` | `ForgeQuerySet` + `ForgeManager` — `.paginate()` |
| `forgeapi/events/bus.py` | `EventBus` singleton + Redis integration |
| `forgeapi/events/redis_bus.py` | Cross-project Redis event bridge |
| `forgeapi/auth/backend.py` | Auth strategies + DI dependencies |
| `forgeapi/permissions/mixins.py` | `PermissionsMixin` abstract base |
| `forgeapi/policies/gate.py` | `Gate` singleton + `Policy` base |
| `forgeapi/cache/cache.py` | `Cache` facade singleton |
| `forgeapi/cache/drivers/` | `MemoryDriver`, `RedisDriver` |
| `forgeapi/support/number.py` | `Number` formatting helpers |
| `forgeapi/support/str_.py` | `Str` string helpers |
| `forgeapi/support/time_.py` | `Time` datetime helpers |
| `forgeapi/telescope/store.py` | Debug store + circular buffer |
| `forgeapi/cli/main.py` | Typer CLI entry point |
| `forgeapi/mcp/server.py` | MCP server entry point |
| `forgeapi/mcp/docs.py` | MCP topic docs database |
| `forgeapi/mcp/examples.py` | MCP code examples database |
| `forgeapi/mcp/generators.py` | MCP code generators |
| `forgeapi/mcp/scanner.py` | MCP AST project scanner |

## Releases

Bump version in `pyproject.toml`, commit, push, then tag:

```bash
git tag v1.x.y
git push origin v1.x.y
```

GitHub Actions (`publish.yml`) publishes to PyPI on tag push.
