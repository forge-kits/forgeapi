# forge-kits — TODO

## [1] Pagination рефактор

### Цель
Убрать offset-based пагинацию как единственный вариант.
Добавить Laravel-style `.paginate()` — один вызов вместо 5 строк в каждом контроллере.
Разбить модуль на подфайлы.

---

### Структура файлов (было → стало)

```
pagination/
├── __init__.py          # был: Paginator, Pagination
│                        # станет: все экспорты + backward compat
├── paginator.py         # был: всё в одном файле
│                        # станет: только OffsetPaginator + .paginate()
├── cursor.py            # NEW — CursorPaginator
└── response.py          # NEW — PaginatedResponse[T], CursorResponse[T], мета-схемы
```

---

### Задачи

#### response.py — новый файл ✅
- [x] `PaginationMeta` — Pydantic схема: current_page, per_page, total, last_page, from_, to
- [x] `PaginationLinks` — Pydantic схема: prev (str|None), next (str|None)
- [x] `PaginatedResponse[T]` — Generic[T]: data: list[T], meta: PaginationMeta, links: PaginationLinks
- [x] `CursorMeta` — per_page, next_cursor (str|None), prev_cursor (str|None)
- [x] `CursorResponse[T]` — Generic[T]: data: list[T], meta: CursorMeta, links: PaginationLinks

#### paginator.py — рефактор ✅
- [x] Параметр переименован в `per_page`, `limit` оставлен как backward compat
- [x] Добавить метод `.paginate(queryset, schema, request)` → `PaginatedResponse[T]`
- [x] Строит links.prev / links.next из request.url
- [x] `_offset` — internal, `offset` — backward compat alias

#### cursor.py — новый файл ✅
- [x] `CursorPaginator` — FastAPI dependency: `?cursor=<base64>&per_page=20`
- [x] +1 трюк: берём per_page+1, если вернулось больше — есть следующая страница
- [x] Метод `.paginate(queryset, schema, order_by="id", request=None)` → `CursorResponse[T]`
- [x] `CursorPagination` — type alias `Annotated[CursorPaginator, Depends()]`

#### __init__.py — обновить ✅
- [x] Экспортировать все новые классы

#### forgeapi/__init__.py — обновить ✅
- [x] Добавлены все новые имена в `_db_exports`

#### Тесты ✅ (35 тестов, 243 всего — все зелёные)
- [x] Все старые тесты проходят
- [x] Тесты PaginatedResponse / CursorResponse структуры
- [x] Тесты encode/decode cursor
- [x] Интеграционные тесты через ASGI

#### CLI — generate:schema
- [ ] Обновить шаблон контроллера: использовать `p.paginate(...)` вместо ручного offset

---

### Пример использования (цель)

```python
# Было (5 строк, в каждом контроллере):
@route.get("/")
async def index(self, p: Pagination):
    total = await Post.all().count()
    items = await Post.all().order_by("-created_at").offset(p.offset).limit(p.limit)
    return {"items": items, "total": total, "page": p.page}

# Стало (1 строка):
@route.get("/")
async def index(self, p: Pagination, request: Request):
    return await p.paginate(Post.all().order_by("-created_at"), PostSchema, request)

# Ответ:
{
  "data": [...],
  "meta": {
    "current_page": 2,
    "per_page": 20,
    "total": 100,
    "last_page": 5,
    "from": 21,
    "to": 40
  },
  "links": {
    "prev": "/posts?page=1&per_page=20",
    "next": "/posts?page=3&per_page=20"
  }
}

# Cursor (бесконечный скролл, нет offset):
@route.get("/")
async def index(self, p: CursorPagination, request: Request):
    return await p.paginate(Post.all(), PostSchema, request)

# Ответ:
{
  "data": [...],
  "meta": {
    "per_page": 20,
    "next_cursor": "eyJpZCI6MTV9",
    "prev_cursor": null
  },
  "links": {
    "prev": null,
    "next": "/posts?cursor=eyJpZCI6MTV9&per_page=20"
  }
}
```

---

## [2] ModelMixin ✅

- [x] `find_or_fail(id, field="id")` — 404 автоматически
- [x] `create_from(payload, **extra)` — `create(**schema.model_dump(exclude_none=True), **extra)`
- [x] `update_from(payload, **extra)` — `update_from_dict + save`
- [x] Экспорт: `from forgeapi import ModelMixin` / `from forgeapi.database import ModelMixin`
- [x] 13 тестов, 256 всего — все зелёные

Использование:
```python
class Post(ModelMixin, Model):
    title = fields.CharField(max_length=255)

    @classmethod
    def published(cls):
        return cls.filter(published=True)

# В контроллере:
post  = await Post.find_or_fail(id)
post  = await Post.create_from(payload, author_id=user.id)
await post.update_from(payload)
posts = await Post.published().order_by("-created_at")
```

## [3] Auth рефактор ✅

Новые файлы:
- `auth/guard.py` — `Guard` класс: strategy + DB model + dependencies
- `auth/facade.py` — `Auth` класс + `auth` singleton
- `auth/dependencies.py` — `CurrentUser`, `OptionalUser` (backward compat)

```python
# Одна стратегия (старый код не ломается):
from forgeapi.auth import CurrentUser, auth
token = auth.token(user)

# Несколько гардов (новый стиль):
from forgeapi.auth import guard
CurrentUser  = guard("api").current_user()    # → User из БД
CurrentAdmin = guard("admin").current_user()  # → Admin из БД

auth.token(user)                  # access token
auth.refresh_token(user)          # refresh token
auth.decode(token)                # decode
auth.token(admin, guard="admin")  # конкретный guard
```

TODO позже:
- [ ] `[auth.guards.*]` в forgeapi.toml — авторегистрация гардов
- [ ] `auth.attempt(email, password)` — проверка пароля
- [ ] Redis blacklist + `auth.logout(user)`
- [ ] Встроенные роуты: POST /auth/login, /auth/refresh, /auth/logout

## [4] API Resources *(следующий этап)*
## [3] Form Requests *(следующий этап)*
## [4] Policies *(следующий этап)*
## [5] Cache фасад *(следующий этап)*
## [6] Разбивка модулей *(параллельно с фичами)*
