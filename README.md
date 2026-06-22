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
7. [Controllers](#7-controllers)
8. [Schemas](#8-schemas)
9. [CLI reference](#9-cli-reference)
10. [forgeapi.toml reference](#10-forgeapitoml-reference)

---

## 1. Quick start

```bash
pip install forgeapi
forgeapi init my-project
cd my-project

# set up DB
tortoise init && tortoise makemigrations && tortoise migrate

forgeapi runserver --reload
```

`forgeapi init` asks two questions: auth strategy (jwt / cookie / telegram) and DB driver (asyncpg / aiosqlite / aiomysql). It scaffolds the full directory tree, `forgeapi.toml`, `.env`, and `main.py`.

---

## 2. Project structure

After `forgeapi init my-project`:

```
my-project/
  main.py                    # entry point — FastAPI app + Core(...)
  forgeapi.toml              # project config
  .env                       # secrets (JWT_SECRET, DB_* etc.)
  pyproject.toml
  app/
    config.py                # TORTOISE_ORM dict
    models/                  # Tortoise models
    controllers/             # *_controller.py files, auto-loaded by Core
    schemas/                 # Pydantic schemas
    events/                  # Event subclasses
    listeners/               # @listen(...) handlers
    migrations/              # aerich / tortoise migrations
```

**`main.py`** looks like this:

```python
from fastapi import FastAPI
from forgeapi import Core
from tortoise.contrib.fastapi import register_tortoise
from app.config import TORTOISE_ORM

app = FastAPI()

core = Core(
    app,
    auth=True,       # reads strategy from forgeapi.toml
    cors=["*"],
    rate_limit=60,
    pagination=20,
    request_id=True,
    events=True,
    # logging=True   ← default, can omit
    # controllers=True ← default, can omit
)

register_tortoise(app, config=TORTOISE_ORM, generate_schemas=False, add_exception_handlers=True)
```

---

## 3. Core

`Core` is the single entry point that wires everything up. Pass it the FastAPI `app` and declare what you need as keyword arguments.

```python
from forgeapi import Core

core = Core(
    app,
    auth=True,
    cors=["*"],
    rate_limit=60,
    pagination=20,
    request_id=True,
    events=True,
    logging=True,       # default True
    controllers=True,   # default True
)
```

### Options

| Argument | Type | Default | Description |
|---|---|---|---|
| `auth` | `bool \| str` | `False` | `True` = strategy from toml; `"jwt"` / `"cookie"` / `"telegram"` = override |
| `cors` | `bool \| list[str]` | `False` | `True` = allow all; list = specific origins |
| `rate_limit` | `bool \| int` | `False` | `True` = 60 req/min; int = custom limit |
| `pagination` | `bool \| int` | `False` | `True` = limits from toml; int = default_limit |
| `request_id` | `bool` | `False` | Injects `X-Request-ID` header into every response |
| `events` | `bool` | `False` | Auto-loads listeners from `listeners_dir` |
| `logging` | `bool` | `True` | Logs method + path + status + duration for every request |
| `controllers` | `bool` | `True` | Auto-imports `*_controller.py` and registers their routers |
| `config_path` | `str` | `"forgeapi.toml"` | Path to the TOML config file |

### Accessing auth after setup

```python
core = Core(app, auth=True)
core.auth           # → AuthBackend instance (or None if auth=False)
core.config         # → KitConfig (parsed forgeapi.toml)
```

### Including routers manually

```python
from app.controllers import admin_router

core.include_router(admin_router)               # prefix: /api/v1
core.include_router(admin_router, prefix="/admin")  # prefix: /api/v1/admin
```

---

## 4. Auth

### How it works

ForgeAPI uses a **Strategy pattern** for authentication. There are three built-in strategies — JWT, Cookie, and Telegram. You pick one in `forgeapi.toml` (or override it in `Core`).

When `Core(app, auth=True)` runs:
1. The chosen strategy is built from `forgeapi.toml` config / env vars.
2. An `AuthBackend` wrapping that strategy is registered as a **global singleton**.
3. The `CurrentUser` and `OptionalUser` type aliases become usable anywhere in your app.

On each request to a protected endpoint FastAPI calls the dependency, which calls `strategy.authenticate(request)`. The strategy reads the credentials (header, cookie), validates them, and returns an `AuthUser` object — or raises `401`.

### CurrentUser and OptionalUser

These are **FastAPI dependency type aliases**. You use them as type annotations in your endpoint functions — FastAPI resolves them automatically.

```python
from forgeapi.auth import CurrentUser, OptionalUser
```

**`CurrentUser`** — required. Returns `AuthUser` or raises `401 Not Authenticated`.

```python
@router.get("/me")
async def me(user: CurrentUser):
    return {"id": user.id, "username": user.username}
```

**`OptionalUser`** — optional. Returns `AuthUser` if credentials are present, `None` otherwise. Never raises 401.

```python
@router.get("/feed")
async def feed(user: OptionalUser):
    if user:
        return personalised_feed(user.id)
    return public_feed()
```

### AuthUser fields

`user` in both cases is an `AuthUser` object:

| Field | Type | Description |
|---|---|---|
| `user.id` | `Any` | User identifier. For JWT/Cookie — value of `"sub"` claim. For Telegram — `telegram_id` (int). |
| `user.username` | `str \| None` | Username if present in token/cookie/initData. |
| `user.auth_method` | `str` | `"jwt"`, `"cookie"`, or `"telegram"`. |
| `user.extra` | `dict` | Any extra claims from the token not in the standard fields. |

```python
async def me(user: CurrentUser):
    print(user.id)           # "42"  (string from JWT sub)
    print(user.username)     # "alice"
    print(user.auth_method)  # "jwt"
    print(user.extra)        # {"role": "admin"} — any custom claims
```

> **Note:** `user.id` from JWT is always a **string** (JWT `sub` is a string). Cast to int when needed: `int(user.id)`.

---

### JWT strategy

Reads credentials from the `Authorization: Bearer <token>` header.

**Config in `forgeapi.toml`:**

```toml
[auth]
strategy = "jwt"
jwt_secret_env = "JWT_SECRET"    # name of the env var with the secret
access_ttl_minutes = 30
refresh_ttl_days = 7
```

**Issuing tokens in a login endpoint:**

```python
from forgeapi.auth.backend import _global_backend

@router.post("/login")
async def login(payload: LoginSchema):
    user = await User.get(username=payload.username)
    # verify password...
    token = _global_backend.strategy.create_access_token({
        "sub": str(user.id),
        "username": user.username,
    })
    return {"access_token": token, "token_type": "bearer"}
```

**Token methods on `JWTStrategy`:**

```python
strategy = _global_backend.strategy  # JWTStrategy

# Issue tokens
access  = strategy.create_access_token({"sub": "42", "username": "alice"})
refresh = strategy.create_refresh_token({"sub": "42"})

# Decode manually (raises 401 on invalid/expired)
payload = strategy.decode(token)
```

The token payload can contain any extra fields — they land in `user.extra`:

```python
token = strategy.create_access_token({"sub": "42", "username": "alice", "role": "admin"})
# later in an endpoint:
user.extra["role"]  # → "admin"
```

---

### Cookie strategy

Stores a signed JSON session in an `HttpOnly` cookie. No token in the Authorization header — authentication happens automatically on every request that carries the cookie.

**Config:**

```toml
[auth]
strategy = "cookie"
cookie_name = "session"
cookie_httponly = true
cookie_secure = false   # set to true in production (HTTPS)
```

**Login — set the cookie:**

```python
from forgeapi.auth.backend import _global_backend
from fastapi import Response

@router.post("/login")
async def login(payload: LoginSchema, response: Response):
    user = await User.get(username=payload.username)
    # verify password...
    _global_backend.strategy.set_cookie(response, {
        "sub": str(user.id),
        "username": user.username,
    })
    return {"detail": "logged in"}
```

**Logout — delete the cookie:**

```python
@router.post("/logout")
async def logout(response: Response):
    _global_backend.strategy.delete_cookie(response)
    return {"detail": "logged out"}
```

The cookie is signed with HMAC-SHA256. If the signature doesn't match on read, the request gets `401`. The secret comes from the `COOKIE_SECRET` env var.

---

### Telegram strategy

Validates the `initData` string that Telegram injects into every Mini App. No login endpoint needed — the backend authenticates on every request automatically.

**Config:**

```toml
[auth]
strategy = "telegram"
```

```bash
# .env
TELEGRAM_BOT_TOKEN=123456:ABC-your-token
```

**How the client sends auth:**

The frontend passes `window.Telegram.WebApp.initData` in either:
- `X-Telegram-Init-Data: <initData>` header (preferred)
- `Authorization: tma <initData>` header

**What you get in `user`:**

```python
async def me(user: CurrentUser):
    user.id           # telegram_id (int)
    user.username     # @username or None
    user.auth_method  # "telegram"
    user.extra        # {"first_name": ..., "last_name": ..., "language_code": ..., "auth_date": ...}
```

**Manual validation (e.g. webhooks):**

```python
from forgeapi.auth.backend import _global_backend

tg_user = _global_backend.strategy.validate_init_data(raw_init_data_string)
# TelegramUser(id=123, username="alice", first_name="Alice", ...)
```

---

## 5. Pagination

Inject `Pagination` as a dependency — it reads `?page` and `?limit` from the query string.

```python
from forgeapi.pagination import Pagination

@router.get("/posts")
async def list_posts(pagination: Pagination):
    total = await Post.all().count()
    items = await Post.all().offset(pagination.offset).limit(pagination.limit)
    return {
        "items": items,
        "total": total,
        "page": pagination.page,
        "limit": pagination.limit,
    }
```

**Query params:**

```
GET /posts?page=2&limit=10
```

| Attribute | Description |
|---|---|
| `pagination.page` | Current page (1-based) |
| `pagination.limit` | Items per page (capped at `MAX_LIMIT`) |
| `pagination.offset` | SQL offset = `(page - 1) * limit` |

**Default limits** come from `forgeapi.toml`:

```toml
[pagination]
default_limit = 20
max_limit = 100
```

Or set via `Core`:

```python
Core(app, pagination=20)   # default_limit=20, max_limit from toml
Core(app, pagination=True) # both limits from toml
```

---

## 6. Events

Events decouple side effects (emails, analytics, cache invalidation) from your business logic.

### Define an event

```python
# app/events/user_registered_event.py
from forgeapi import Event

class UserRegisteredEvent(Event):
    background = True   # fire-and-forget — doesn't block the HTTP response

    def __init__(self, user_id: int, email: str) -> None:
        self.user_id = user_id
        self.email   = email
```

`background = True` — listeners run in a background task, the response is returned immediately.  
`background = False` (default) — all listeners are awaited before the response is sent.

### Register a listener

```python
# app/listeners/user_registered_listener.py
from forgeapi import listen
from app.events.user_registered_event import UserRegisteredEvent

@listen(UserRegisteredEvent)
async def send_welcome_email(event: UserRegisteredEvent) -> None:
    await mailer.send(event.email, subject="Welcome!")
```

Multiple listeners for the same event run **in parallel** via `asyncio.gather`.

### Dispatch from a route

```python
await UserRegisteredEvent(user_id=user.id, email=user.email).dispatch()
```

### Auto-loading listeners

`Core(app, events=True)` imports every `*.py` file in `listeners_dir` (default: `app/listeners`). Since `@listen(...)` registers on import, you don't need to do anything else.

Listeners are loaded before the first request — put `Core(app, events=True)` in `main.py`.

---

## 7. Controllers

A controller is a class that registers its routes in `__init__` on a module-level `router`.

```python
# app/controllers/post_controller.py
from fastapi import APIRouter, HTTPException
from forgeapi.auth import CurrentUser
from forgeapi.pagination import Pagination
from app.models import Post

router = APIRouter(prefix="/posts", tags=["posts"])

class PostController:
    def __init__(self) -> None:
        router.add_api_route("/",          self.index,  methods=["GET"])
        router.add_api_route("/",          self.create, methods=["POST"])
        router.add_api_route("/{post_id}", self.show,   methods=["GET"])

    async def index(self, pagination: Pagination) -> dict:
        items = await Post.all().offset(pagination.offset).limit(pagination.limit)
        return {"items": items, "total": await Post.all().count()}

    async def create(self, payload: PostCreateSchema, user: CurrentUser) -> Post:
        return await Post.create(**payload.model_dump(), author_id=int(user.id))

    async def show(self, post_id: int) -> Post:
        post = await Post.get_or_none(id=post_id)
        if not post:
            raise HTTPException(404, "Not found")
        return post
```

No need to call `PostController()` at the bottom — `Core` instantiates it automatically when loading.

`Core(app, controllers=True)` (default) scans `controllers_dir` for all `*_controller.py` files, imports them, and if the `router` is empty, instantiates the controller class to register routes. All routers are included under `base_prefix` (default `/api/v1`).

### Generating a controller

```bash
forgeapi make:controller Post          # controller only
forgeapi make:controller Post --ms     # controller + model + schema
forgeapi make:model Post --cs          # model + controller + schema
```

---

## 8. Schemas

Three base schema classes cover the standard CRUD pattern.

```python
from forgeapi import BaseSchema, BaseCreateSchema, BaseUpdateSchema
```

### BaseSchema — response

Adds `id`, `created_at`, `updated_at`. Has `from_attributes=True` so it reads directly from Tortoise model instances.

```python
class PostSchema(BaseSchema):
    title: str
    body:  str

# in a route:
return PostSchema.model_validate(post)   # post is a Tortoise model instance
```

### BaseCreateSchema — POST payload

Plain `BaseModel` subclass. All fields required unless you add defaults.

```python
class PostCreateSchema(BaseCreateSchema):
    title: str
    body:  str
    is_published: bool = True
```

### BaseUpdateSchema — PATCH payload

Same as `BaseCreateSchema`. Convention: make all fields `Optional` so partial updates work.

```python
class PostUpdateSchema(BaseUpdateSchema):
    title: str | None = None
    body:  str | None = None
```

```python
# applying a partial update in a route:
for field, value in payload.model_dump(exclude_none=True).items():
    setattr(post, field, value)
await post.save()
```

### Generating schemas from an existing model

```bash
forgeapi generate:schema Post
```

Reads the Tortoise model's `_meta.fields_map`, maps field types to Python types, and generates all three schema classes with correct optionality. Run from the project root with the model already defined.

---

## 9. CLI reference

### `forgeapi init <project-name>`

Scaffold a new project. Asks for auth strategy and DB driver.

### `forgeapi make:controller <Name> [flags]`

Generate a controller. Flags add related files:

| Flag | Short | Generates |
|---|---|---|
| `--model` | `-m` | Tortoise model |
| `--schema` | `-s` | Pydantic schemas (3 classes) |

Compound: `--ms` = model + schema.

```bash
forgeapi make:controller User --ms     # controller + model + schema
```

### `forgeapi make:model <Name> [flags]`

Generate a Tortoise model. Optional flags: `--controller` (`-c`), `--schema` (`-s`).

```bash
forgeapi make:model Post -cs           # model + controller + schema
```

### `forgeapi make:schema <Name> [flags]`

Generate stub schemas. Optional flags: `--model` (`-m`), `--controller` (`-c`).

### `forgeapi make:event <Name>`

Generate an event class in `events_dir`.

```bash
forgeapi make:event UserRegistered
# creates app/events/user_registered_event.py
```

### `forgeapi make:listener <Name>`

Generate a listener file in `listeners_dir` with the import and `@listen` decorator pre-filled.

```bash
forgeapi make:listener UserRegistered
# creates app/listeners/user_registered_listener.py
```

### `forgeapi generate:schema <ModelName>`

Generate schemas from an **existing** Tortoise model by reading its field metadata at runtime. More accurate than the stub generated by `make:schema`.

```bash
forgeapi generate:schema Post
```

### `forgeapi runserver [options]`

Start the development server via uvicorn.

```bash
forgeapi runserver --port 8000 --host 0.0.0.0 --reload
```

---

## 10. forgeapi.toml reference

```toml
[project]
name = "my-app"
version = "0.1.0"

[structure]
models_dir      = "app/models"
controllers_dir = "app/controllers"
schemas_dir     = "app/schemas"
events_dir      = "app/events"
listeners_dir   = "app/listeners"
base_prefix     = "/api/v1"

[auth]
strategy             = "jwt"           # jwt | cookie | telegram
jwt_secret_env       = "JWT_SECRET"   # env var name that holds the secret
access_ttl_minutes   = 30
refresh_ttl_days     = 7

# cookie-only fields:
cookie_name          = "session"
cookie_httponly      = true
cookie_secure        = false           # set true in production

[pagination]
default_limit = 20
max_limit     = 100
```

The config file is optional — all fields have sensible defaults and `Core` works without it.
