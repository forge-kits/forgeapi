# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

**forge-kits** (`import forgeapi`) — a FastAPI toolkit that adds controllers, events, permissions, auth, cache, and CLI scaffolding on top of FastAPI. All features are optional and wired together via the `Core` class.

Published to PyPI as `forge-kits`. Requires Python 3.11+.

## Design Principles

forge-kits is a **Laravel-style framework in Python**. When designing new features or refactoring, think "how does Laravel solve this?" first, then translate to Python/FastAPI idioms. The mapping so far:

| Laravel | forge-kits |
|---------|-----------|
| Service Provider | `Core` wiring (should orchestrate registration, not contain module logic) |
| Facade | Module-level singletons: `Cache`, `gate`, `auth`, `EventBus` |
| Eloquent | `ModelMixin` + Tortoise (`find_or_fail`, `create_from`, `.paginate()`) |
| Artisan | `forgeapi` CLI (`make:*`, `db:*`) |
| Gate / Policy | `forgeapi/policies/` |
| spatie/laravel-permission | `forgeapi/permissions/` (same pivot-table design) |
| Events / Listeners | `forgeapi/events/` |
| Middleware / Route guards | `Middleware` + `Guard` |
| `Str` / `Number` / Carbon | `forgeapi/support/` |
| Telescope | `forgeapi/telescope/` |

### API surface

- **Public vs private is explicit, not implied.** Anything not meant to be imported by users gets a `_` prefix or lives in an `internal/` module. "Just not documented" is not private. If the docs tell users to import something underscore-prefixed (e.g. a `_global_backend`), that's a design bug — rename/re-export it properly.
- **One way to do a thing.** Each feature has one primary path (`Core(app)` + `config/` sections); manual wiring (`auth.register()`, `core.use()`) is an explicit escape hatch, not an equal alternative. Never add a second equivalent API for convenience.
- **Stable core, experimental edge.** Auth, Controllers, Schemas, ModelMixin — breaking changes here are expensive; design carefully (see Versioning for the current breaking-change policy). Telescope, Policies — may still churn freely until they settle.
- **Zero-config must work.** `Core(app)` with no config files must not raise. This is the first thing every new user tries; keep a test asserting it.
- **`Core` is not a God Object.** It wires and delegates. Module logic (cache setup, event loading, auth backend construction) lives in the module's own package; `Core` only calls a register/setup entry point. If `Core` starts accumulating per-module logic, extract a Service Provider–style registration hook instead.

### Extension points

If a third implementation of something is plausible (auth strategy, cache driver, event transport), define the interface **first** — a `Protocol` or ABC in the module's package — then implement against it. Existing extension points: auth strategies (jwt/cookie/telegram), cache drivers (memory/redis), event transports (in-process/pubsub/stream). New strategies/drivers must implement the shared interface, never duck-type against one concrete class.

### Behavioural consistency (especially auth)

All auth strategies must behave **identically at the edges**. For every strategy, these cases return the same exception type and the same error body shape:

- missing header/cookie/initData
- expired token/signature
- invalid signature
- valid token, but user no longer in DB

This is enforced structurally, not by tests: strategies may raise **only**
`ForgeAPIAuthError` subclasses (never `HTTPException`), and `Guard.authenticate`
is the single point translating them to HTTP 401. A new strategy that follows
the contract is consistent by construction. (Matrix testing across strategies
was considered and rejected — the user prefers the structural guarantee.)
Prefer edge-case tests over happy-path tests — the happy path gets checked by hand anyway.

### Versioning & breaking changes

- Semver, with a **solo-user phase caveat** (decided 2026-07): while the author
  is the only user, breaking changes land directly — no deprecation cycle, no
  compat shims — but every one is recorded in `CHANGELOG.md`
  (Added / Changed / Removed per version). Once there are external users,
  switch to deprecate-before-delete (`warnings.warn(..., DeprecationWarning)`
  for at least one minor release).
- Never silently remove or rename a public symbol — CHANGELOG entry always.
- Public docstrings carry a short usage example — future-you is the first user who forgets why a flag exists.

### Documentation

`README.md` is the reference (what exists). Any new user-facing feature also needs a **getting-started narrative** angle — the "build a blog API in 5 minutes" path is what converts a PyPI visitor into a user. When adding a feature, ask: where does it appear in that 5-minute story?

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
- `project_info(path)` — Read the project config and list project files (NOTE: still reads legacy forgeapi.toml — pending update to config/)

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

### Entry point: `Core` (forgeapi/kit.py) + Providers (forgeapi/foundation/)

**`Core(app)` takes only the app** — everything else is config-driven,
convention over configuration:

```python
from fastapi import FastAPI
from forgeapi import Core

app = FastAPI()
Core(app)   # the entire wiring
```

What runs is decided by `config/`:
- middleware stack — `config/http.py` (cors, rate_limit, request_id, access_log, middleware)
- auth guards — boot when `config/auth.py` exists
- Telescope — `"debug": True` in `config/project.py` (never in production)
- permissions — boot automatically when a model in `models_dir` inherits `PermissionsMixin` (no config file)
- controllers / listeners / policies — boot when their directory exists
- pagination and cache — always configured (from their sections or defaults)
- custom providers — `"providers"` in `config/project.py`

`Core` is a **thin orchestrator** (Service Provider pattern): it collects
module `Provider`s, runs `register()` on all, then `boot()` on all. Module
wiring logic lives in `forgeapi/<module>/provider.py`, never in Core.

Provider phase rules (`forgeapi/foundation/provider.py`):
- `register()` — configure the module itself (facades, middleware). Must NOT import user code.
- `boot()` — runs after all `register()`s. Discovery that imports user code
  (controllers, listeners, policies, models, auth guard models) goes here, so
  user modules see fully configured facades at import time.

`Core(app)` with no config files must never raise — covered by tests.

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

`setup_permissions(UserModel)` must be called before queries. `Core(app)` does this automatically: `PermissionProvider` scans `models_dir` and activates when it finds the single `PermissionsMixin` subclass (silently skips when there is none).

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

Strict layer hierarchy (each layer's knowledge is capped):

```
Auth (facade)   — guard registry + strategy factories. Pure delegation, zero logic.
 └─ Guard       — strategy + user model. The ONLY layer that speaks HTTP (401)
                  and touches the DB (get_or_none). Single domain-error → HTTP
                  translation point.
     └─ AuthStrategy — pure domain: extract/verify credentials, issue tokens.
                  Raises ONLY ForgeAPIAuthError subclasses. Never HTTPException,
                  never DB, never user models.
```

Built-in strategies: **jwt** (Bearer header), **cookie** (HMAC-signed HttpOnly
cookie), **telegram** (Mini App `initData`). Custom strategies register via
`auth.extend("apikey", ApiKeyStrategy)`; every strategy implements
`from_config(cfg: dict)`.

Capabilities are protocols (`forgeapi/auth/contracts.py`): `TokenIssuer`,
`RefreshCapable`, `SessionIssuer`. `Guard.token()/decode()/set_cookie()`
dispatch on `isinstance(strategy, Protocol)` — never on concrete classes.

Error semantics (uniform across strategies):
- credentials **absent** → `None` from strategy; Guard: 401 if required, `None` if optional
- credentials **present but invalid** (expired / bad signature / user gone from DB)
  → domain exception → 401 **always**, even for `OptionalUser`
- 401s carry `WWW-Authenticate: Bearer error="<code>"` (code from the exception:
  `token_expired`, `session_invalid`, `user_not_found`, ...)

```python
from forgeapi.auth import CurrentUser, OptionalUser, auth, guard

@route.get("/me")
async def me(user: CurrentUser): ...      # 401 if missing

# multi-guard (guards defined in config/auth.py):
CurrentAdmin = guard("admin").current_user()

access  = auth.token(user)           # access token (takes DB model instance)
refresh = auth.refresh_token(user)   # refresh token (RefreshCapable strategies)
payload = auth.decode(token, expected_type="access")  # verify + decode

# SessionIssuer (cookie) strategies:
auth.set_cookie(response, {"sub": str(user.id), "username": user.username})
auth.delete_cookie(response)
```

Token claims: define `auth_claims() -> dict` on the user model to control
what goes into tokens (`sub` is auto-filled from `user.id`).

### Cache (forgeapi/cache/)

Async key-value cache with memory (default) and Redis drivers. Configured automatically by `Core` from `config/cache.py`.

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

### Configuration (forgeapi/config/)

The only format: **`config/` directory of Python dict files** (Laravel-style).
Each `config/<section>.py` defines a module-level `config = {...}`; the
filename is the section name. All sections optional. (`forgeapi.toml` is gone —
`load_config` raises on it with a migration hint.)

```python
# config/project.py
from forgeapi import env
config = {"name": "my-app", "debug": env("APP_DEBUG", False), "providers": []}

# config/http.py
config = {"cors": ["*"], "rate_limit": 60, "request_id": True,
          "access_log": True, "middleware": []}

# config/auth.py
config = {
    "default": "api",
    "guards": {
        "api":   {"strategy": "jwt", "secret": env("JWT_SECRET"),
                  "access_ttl": 30, "model": "database.models.user.User"},
        "admin": {"strategy": "jwt", "secret": env("ADMIN_JWT_SECRET")},
    },
}

# config/cache.py
config = {"driver": "memory", "prefix": "", "ttl": 3600,
          "redis_url": "redis://localhost:6379/0"}

# config/database.py — the TORTOISE_ORM dict lives HERE (not in app/);
# that's all the file needs — the loader derives the importable dotted path
# for the tortoise CLI (config/ is a namespace package). An explicit
# config = {"tortoise_orm": "app.settings.ORM"} overrides for non-standard
# locations only.
TORTOISE_ORM = {"connections": {...}, "apps": {...}}
```

- `env("KEY", default)` reads env vars (casts `"true"`/`"false"`/`"null"`).
- Custom sections are allowed (`config/services.py`) and reachable via dot
  access: `cfg.get("services.stripe.key", default)`.
- Known sections are validated by Pydantic models in `forgeapi/config/models.py`.
- `KitConfig.provided("auth")` tells whether a section came from the user —
  feature enablement is decided by section presence.

### CLI (forgeapi/cli/)

Built with Typer + Rich. Code generation uses Jinja2 templates in `forgeapi/cli/templates/`. `forgeapi init` scaffolds a full project with Tortoise ORM, auth, and a sample controller.

## Key Files

| File | Purpose |
|------|---------|
| `forgeapi/kit.py` | `Core` — thin provider orchestrator |
| `forgeapi/foundation/provider.py` | `Provider` base (register/boot phases) |
| `forgeapi/config/models.py` | `KitConfig` + section models |
| `forgeapi/config/loader.py` | `load_config` — config/ dir + toml fallback |
| `forgeapi/config/env.py` | `env()` helper for config files |
| `forgeapi/controllers/base.py` | `Controller` + `@route` |
| `forgeapi/database/model.py` | `ModelMixin` — find_or_fail, create_from, update_from |
| `forgeapi/database/queryset.py` | `ForgeQuerySet` + `ForgeManager` — `.paginate()` |
| `forgeapi/events/bus.py` | `EventBus` singleton + Redis integration |
| `forgeapi/events/redis_bus.py` | Cross-project Redis event bridge |
| `forgeapi/auth/facade.py` | `Auth` facade — guard registry + `extend()` |
| `forgeapi/auth/guard.py` | `Guard` — domain-error → HTTP translation point |
| `forgeapi/auth/contracts.py` | `TokenIssuer` / `RefreshCapable` / `SessionIssuer` protocols |
| `forgeapi/auth/provider.py` | `AuthProvider` — builds guards from config |
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
