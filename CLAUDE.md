# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

**forge-kits** (`import forgeapi`) — a FastAPI toolkit that adds controllers, events, permissions, auth, and CLI scaffolding on top of FastAPI. All features are optional and wired together via the `Core` class.

Published to PyPI as `forge-kits`. Requires Python 3.11+.

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

### Controllers (forgeapi/controllers/base.py)

Route classes that auto-register with FastAPI. CamelCase name → URL prefix:
- `PostController` → `/posts`
- `AdminUserController` → `/admin/users`

```python
class PostController(Controller):
    prefix = "/posts"   # optional override
    tags = ["posts"]
    guards = [SomeGuard()]

    @route.get("/")
    async def index(self, pagination: Pagination): ...

    @route.post("/", status_code=201)
    async def create(self, payload: PostCreate, user: CurrentUser): ...
```

`@route` mirrors FastAPI's decorators (`get`, `post`, `put`, `patch`, `delete`).

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

Spatie-style polymorphic RBAC. The user model inherits `PermissionsMixin` — no extra columns needed on the model itself. All assignments live in shared pivot tables (`model_has_roles`, `model_has_permissions`).

```python
await user.give_permission("edit:posts")
await user.assign_role("admin")
await user.can("edit:posts")     # → bool
await user.has_role("admin")     # → bool

# FastAPI dependencies
@route.delete("/{id}")
async def destroy(self, id: int, user=require_permission("delete:posts")): ...
```

`setup_permissions(UserModel)` must be called before queries. `Core(permissions=True)` does this automatically when it detects a `PermissionsMixin` subclass.

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

token = auth.create_access_token({"sub": str(user.id)})
```

### Schemas (forgeapi/schemas/base.py)

Three base classes: `BaseSchema` (read/response), `BaseCreateSchema`, `BaseUpdateSchema`. All fields in `BaseUpdateSchema` are optional by default.

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
```

### CLI (forgeapi/cli/)

Built with Typer + Rich. Code generation uses Jinja2 templates in `forgeapi/cli/templates/`. `forgeapi init` scaffolds a full project with Tortoise ORM, auth, and a sample controller.

## Key Files

| File | Purpose |
|------|---------|
| `forgeapi/kit.py` | `Core` class — main wiring |
| `forgeapi/config.py` | `KitConfig` — TOML config model |
| `forgeapi/controllers/base.py` | `Controller` + `@route` |
| `forgeapi/events/bus.py` | `EventBus` singleton + Redis integration |
| `forgeapi/events/redis_bus.py` | Cross-project Redis event bridge |
| `forgeapi/auth/backend.py` | `AuthBackend` + DI dependencies |
| `forgeapi/permissions/mixins.py` | `PermissionsMixin` abstract base |
| `forgeapi/telescope/store.py` | Debug store + circular buffer |
| `forgeapi/cli/main.py` | Typer CLI entry point |

## Releases

Bump version in `pyproject.toml`, commit, push, then tag:

```bash
git tag v0.x.y
git push origin v0.x.y
```

GitHub Actions (`publish.yml`) publishes to PyPI on tag push.
