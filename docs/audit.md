# ForgeAPI — Code Audit

71 raw findings → **56 confirmed** after adversarial verification.

---

## Security

### HIGH

#### JWT: refresh token accepted as access token
**File:** `forgeapi/auth/strategies/jwt.py:164`

`authenticate()` calls `decode()` which verifies signature and expiry but never checks the `type` claim. A long-lived refresh token (`type="refresh"`, 7-day TTL) passes `authenticate()` and grants access to any protected endpoint.

**Fix:**
```python
# in authenticate(), after decode():
if payload.get("type") != "access":
    raise HTTPException(status_code=401, detail="Invalid token type")
```

---

#### Telegram: initData without `user` field authenticates as `id=0`
**File:** `forgeapi/auth/strategies/telegram.py:131`

When initData has a valid HMAC but no `user` field (bot updates, background webhooks), `user_raw` is empty, `json.loads("{}")` returns `{}`, and `user_data.get("id", 0)` returns `0`. The resulting `AuthUser(id=0)` is truthy — the request is considered fully authenticated with user id `0`.

**Fix:**
```python
tg_id = user_data.get("id", 0)
if not tg_id:
    raise HTTPException(status_code=401, detail="No user in Telegram init data")
```

---

### MEDIUM

#### `int(auth_user.id)` raises unhandled ValueError → HTTP 500
**File:** `forgeapi/permissions/dependencies.py:29, 60`

Both `RequirePermission` and `RequireRole` call `int(auth_user.id)` unconditionally. `AuthUser.id` is typed `Any` and can be a UUID string, `None`, or any non-integer value depending on the auth strategy. This raises `ValueError` → unhandled 500 instead of 401.

**Fix:**
```python
try:
    user_id = int(auth_user.id)
except (TypeError, ValueError):
    raise HTTPException(status_code=401, detail="Invalid user identity")
```

---

#### Telegram: non-integer `auth_date` raises unhandled ValueError → HTTP 500
**File:** `forgeapi/auth/strategies/telegram.py:105`

`int(params.get("auth_date", 0))` raises `ValueError` if `auth_date` is present but not a valid integer (e.g. `auth_date=abc`). Propagates as 500.

**Fix:**
```python
try:
    auth_date = int(params.get("auth_date", 0))
except ValueError:
    raise HTTPException(status_code=401, detail="Invalid auth_date in Telegram init data")
```

---

#### Telegram: malformed `user` JSON field raises unhandled JSONDecodeError → HTTP 500
**File:** `forgeapi/auth/strategies/telegram.py:136`

`json.loads(user_raw or "{}")` has no `try/except`. A crafted initData with a syntactically invalid `user` field causes `json.JSONDecodeError` → 500.

**Fix:**
```python
try:
    user_data = json.loads(user_raw or "{}")
except (json.JSONDecodeError, ValueError):
    raise HTTPException(status_code=401, detail="Malformed user field in Telegram init data")
```

---

#### Telegram: future-dated `auth_date` is silently accepted
**File:** `forgeapi/auth/strategies/telegram.py:105`

The expiry check is `age > self._max_age` where `age = time.time() - auth_date`. When `auth_date` is in the future `age` is negative and always passes — making the token permanently valid.

**Fix:**
```python
if age < 0 or age > self._max_age:
    raise HTTPException(status_code=401, detail="Telegram init data timestamp is invalid")
```

---

#### `CookieStrategy` defaults `secure=False` — cookies sent over plain HTTP
**File:** `forgeapi/auth/strategies/cookie.py:60`, `forgeapi/config.py:44`

Both `CookieStrategy.__init__` and `AuthTomlConfig` default `secure=False`. Any production deployment that does not explicitly set `secure=True` transmits session cookies over unencrypted HTTP.

**Fix:** Change defaults to `secure: bool = True` in both places. Add a `logger.warning` when `secure=False` is used.

---

#### `RequirePermission` returns 403 for a deleted user (should be 401)
**File:** `forgeapi/permissions/dependencies.py:32`

When a valid token references a user that no longer exists in the DB, `get_or_none` returns `None` and `HTTPException(403)` is raised. HTTP 403 leaks information — the token was accepted but the account is gone. The correct status is 401.

**Fix:**
```python
if not db_user:
    raise HTTPException(status_code=401, detail="User not found")
```

---

#### Rate limiter reads `request.client.host` — ineffective behind a reverse proxy
**File:** `forgeapi/middleware/rate_limit.py:21`

When the app runs behind nginx / AWS ALB / Cloudflare, `request.client.host` is always the proxy's IP. All real clients share one rate-limit bucket (immediately throttled) or the proxy itself gets blocked.

**Fix:** Read `X-Forwarded-For` or `X-Real-IP` when a trusted proxy is configured.

---

## N+1 Queries

All N+1 issues are in `forgeapi/permissions/mixins.py` and `forgeapi/permissions/models.py`.

### Summary table

| Method | File | Queries now | Should be |
|---|---|---|---|
| `has_all_permissions()` | `mixins.py:68` | 2N (loop over `can()`) | 2 |
| `has_all_roles()` | `mixins.py:140` | 2N (loop over `has_role()`) | 2 |
| `give_permission()` | `mixins.py:101` | 4N (find_or_create + get_or_create per perm) | 2 |
| `revoke_permission()` | `mixins.py:110` | 2N (get_or_none + delete per perm) | 2 |
| `assign_role()` | `mixins.py:158` | 4N (find_or_create + get_or_create per role) | 2 |
| `remove_role()` | `mixins.py:167` | 2N (get_or_none + delete per role) | 2 |
| `get_role_names()` | `mixins.py:147` | 2 (IDs then names) | 1 (JOIN) |
| `Role.give_permission()` | `models.py:44` | 2N (find_or_create + M2M add per perm) | 2 |
| `Role.revoke_permission()` | `models.py:49` | 2N (get_or_none + M2M remove per perm) | 2 |

### `has_all_permissions` / `has_all_roles`

**Fix** — reuse the already-existing `get_all_permissions()`:
```python
async def has_all_permissions(self, *permissions: str) -> bool:
    all_perms = set(await self.get_all_permissions())
    return set(permissions).issubset(all_perms)

async def has_all_roles(self, *roles: str) -> bool:
    requested_ids = set(
        await Role.filter(name__in=list(roles)).values_list("id", flat=True)
    )
    if len(requested_ids) != len(roles):
        return False
    held_ids = set(
        await ModelHasRole.filter(
            model_type=self._model_type,
            model_id=self.pk,
            role_id__in=list(requested_ids),
        ).values_list("role_id", flat=True)
    )
    return held_ids == requested_ids
```

### `give_permission` / `assign_role`

**Fix** — bulk fetch + bulk insert:
```python
async def give_permission(self, *permissions: str) -> None:
    existing = await Permission.filter(name__in=list(permissions)).all()
    existing_names = {p.name for p in existing}
    new_perms = await Permission.bulk_create(
        [Permission(name=n) for n in permissions if n not in existing_names],
        ignore_conflicts=True,
    )
    all_perms = existing + new_perms
    await ModelHasPermission.bulk_create(
        [ModelHasPermission(model_type=self._model_type, model_id=self.pk, permission_id=p.pk) for p in all_perms],
        ignore_conflicts=True,
    )
```

### `revoke_permission` / `remove_role`

**Fix** — single IN query + single delete:
```python
async def revoke_permission(self, *permissions: str) -> None:
    perm_ids = await Permission.filter(name__in=list(permissions)).values_list("id", flat=True)
    if perm_ids:
        await ModelHasPermission.filter(
            model_type=self._model_type,
            model_id=self.pk,
            permission_id__in=list(perm_ids),
        ).delete()

async def remove_role(self, *roles: str) -> None:
    role_ids = await Role.filter(name__in=list(roles)).values_list("id", flat=True)
    if role_ids:
        await ModelHasRole.filter(
            model_type=self._model_type,
            model_id=self.pk,
            role_id__in=list(role_ids),
        ).delete()
```

### `get_role_names`

**Fix** — single query with JOIN:
```python
async def get_role_names(self) -> list[str]:
    return list(
        await ModelHasRole.filter(
            model_type=self._model_type,
            model_id=self.pk,
        ).values_list("role__name", flat=True)
    )
```

### `Role.give_permission` / `Role.revoke_permission`

**Fix** — batch M2M operations:
```python
async def give_permission(self, *names: str) -> None:
    existing = await Permission.filter(name__in=list(names)).all()
    existing_names = {p.name for p in existing}
    created = await Permission.bulk_create(
        [Permission(name=n) for n in names if n not in existing_names],
        ignore_conflicts=True,
    )
    await self.permissions.add(*existing, *created)

async def revoke_permission(self, *names: str) -> None:
    perms = await Permission.filter(name__in=list(names)).all()
    if perms:
        await self.permissions.remove(*perms)
```

---

## Bugs

### HIGH

#### `asyncio.create_task()` without a strong reference — tasks silently GC'd
**File:** `forgeapi/events/bus.py:292` and `:182`

`asyncio.create_task()` is called without storing the returned `Task`. The Python GC can collect a task with no remaining references before it finishes — all listeners are cancelled silently with no log output. This is a non-deterministic race under load.

**Fix:**
```python
# In EventBus.__init__:
self._bg_tasks: set = set()

# When creating a task:
t = asyncio.create_task(self._run_all(event, listeners), name=f"event:{type(event).__name__}")
self._bg_tasks.add(t)
t.add_done_callback(self._bg_tasks.discard)
```

---

#### `_import_file` deduplication uses only the file stem — silent collision
**File:** `forgeapi/events/bus.py:341`

The dedup key is `_fk_listener_{path.stem}`. Two files named `orders.py` in different directories both produce `_fk_listener_orders`. The second file is silently skipped — all its `@listen` registrations are lost with no warning.

**Fix:**
```python
import hashlib
module_name = f"_fk_listener_{hashlib.md5(str(path.resolve()).encode()).hexdigest()}"
```

---

#### `int(auth_user.id)` raises unhandled ValueError → HTTP 500
**File:** `forgeapi/permissions/dependencies.py:29, 60`

*(See Security section above — same issue, listed here as a bug too because it crashes the server.)*

---

### MEDIUM

#### `EventBus.reset()` leaks the Redis subscriber task and its connection
**File:** `forgeapi/events/bus.py:93`

`reset()` sets `cls._instance = None` but does not cancel the background `asyncio.Task` running `start_redis_subscriber()`. That task holds a live Redis pubsub connection and continues running forever against the now-orphaned instance. In test suites this produces a connection leak that accumulates across the test session.

**Fix:** Track the subscriber task on the instance and cancel it in `reset()`:
```python
@classmethod
def reset(cls) -> None:
    if cls._instance and hasattr(cls._instance, "_subscriber_task"):
        task = cls._instance._subscriber_task
        if task and not task.done():
            task.cancel()
    cls._instance = None
```

---

#### `_load_controllers` does not catch `ImportError` — crashes startup
**File:** `forgeapi/kit.py:283`

`importlib.import_module(module_path)` has no `try/except`. Any `SyntaxError`, `ImportError`, or other exception in a controller file propagates out of `_load_controllers` and crashes `Core.__init__` with no message identifying which file failed.

**Fix:**
```python
try:
    mod = importlib.import_module(module_path)
except Exception as exc:
    logger.error("Failed to load controller '%s': %s", f, exc, exc_info=exc)
    continue
```

---

#### `LoggingMiddleware` silently drops log entries when `call_next` raises
**File:** `forgeapi/middleware/logging.py:14`

If `call_next` raises an exception (unhandled 500), the `logger.info` line is never reached. Failed requests produce no access log entry, making production debugging harder.

**Fix:**
```python
async def dispatch(self, request, call_next):
    start = time.perf_counter()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        return response
    finally:
        logger.info("%s %s %d %.3fs", request.method, request.url.path, status, time.perf_counter() - start)
```

---

#### `without_role` returns ALL instances when role doesn't exist
**File:** `forgeapi/permissions/mixins.py:195`

If none of the requested roles exist in the DB, `ids` is `[]` and `cls.exclude(id__in=[])` returns every row in the table. Semantically correct but surprising when a role name is misspelled.

**Fix:** Document this behaviour explicitly, or add a guard that returns an empty queryset when the role names don't exist in the `Role` table.

---

#### `Paginator.configure()` accepts `max_limit=0` or negative — breaks all queries
**File:** `forgeapi/pagination/paginator.py:56`

No validation in `configure()`. If called with `max_limit=0`, `min(resolved_limit, 0)` returns `0`, meaning every query uses `LIMIT 0` and returns no rows.

**Fix:**
```python
@classmethod
def configure(cls, default_limit: int = 20, max_limit: int = 100) -> None:
    if default_limit < 1 or max_limit < 1:
        raise ValueError("default_limit and max_limit must be >= 1")
    cls.DEFAULT_LIMIT = default_limit
    cls.MAX_LIMIT = max_limit
```

---

## Performance

### `RequirePermission` re-fetches the DB user on every request
**File:** `forgeapi/permissions/dependencies.py:27`

Every permission-guarded request calls `UserModel.get_or_none(id=...)` even though the auth layer already validated the user. Combined with `can()` (2–3 queries), each protected endpoint makes 4+ DB round-trips per request. `RequireRole` has the same issue.

**Recommended fix:** Cache the resolved DB user on `request.state`:
```python
async def _check(auth_user: CurrentUser, request: Request):
    if not hasattr(request.state, "db_user"):
        request.state.db_user = await UserModel.get_or_none(id=int(auth_user.id))
    db_user = request.state.db_user
    ...
```

---

### `RateLimitMiddleware._store` grows unbounded
**File:** `forgeapi/middleware/rate_limit.py:18`

`_store` is a `defaultdict(deque)` keyed by client IP. Empty deques are pruned per-request but their keys are never removed from the dict. On a public service hit by many unique IPs the dict grows forever.

**Fix:** Delete the key when its deque becomes empty:
```python
if not self._store[client_ip]:
    del self._store[client_ip]
```

---

### UUID4 generated in `__new__` then discarded in `from_dict()`
**File:** `forgeapi/events/event.py:59`

`Event.__new__` unconditionally calls `str(uuid.uuid4())` (a syscall). When `from_dict()` reconstructs an event, this UUID is immediately overwritten by `__dict__.update(data)`. Under high-volume Redis processing every deserialization wastes a `uuid4()` call.

**Fix:** Move `event_id` assignment into `__init__` instead of `__new__`, so `from_dict()` (which calls `__new__` directly without `__init__`) skips it.
