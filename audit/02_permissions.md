# Аудит: Permissions модуль

## Краткое резюме

Модуль permissions содержит 14 отдельных находок, охватывающих безопасность, производительность, гонки состояний, типобезопасность и стиль кода. Наиболее серьёзные проблемы: (1) путь эскалации привилегий, при котором `assign_role` молча автосоздаёт любое переданное имя роли, что позволяет атакующему, способному вызвать этот метод, изобретать и назначать себе произвольные роли; (2) две неатомарные TOCTOU-гонки в `sync_permissions` и `sync_roles`, допускающие устаревшее состояние прав при конкурентных запросах; (3) каждая проверка прав в `dependencies.py` выполняет 2–3 последовательных обращения к БД на запрос без какого-либо кэширования, что делает нагруженные эндпоинты дорогостоящими; (4) быстрый путь `can()` проверяет только прямые права и затем отдельно запрашивает role_ids, поэтому пользователь с прямым запретом и ролевым разрешением одновременно может пройти проверку в зависимости от порядка данных; (5) `has_all_roles` содержит логическую ошибку при передаче дублирующихся имён ролей. Дополнительные находки среднего уровня касаются отсутствия фильтрации по полю guard в RBAC-запросах, утечки информации через сообщения ошибок 403, небезопасности глобального синглтона `_user_model` в многоприложных окружениях, а также ряда проблем с типами и стилем кода.

## Находки

### [CRITICAL] Security - Privilege Escalation — assign_role и give_permission молча автосоздают произвольные роли и права

**Файл:** permissions/mixins.py:175-196, permissions/models.py:44-56
**Серьёзность:** Критическая

**Описание:**
И `assign_role`, и `give_permission` (а также их аналоги на `Role`) используют паттерн: запросить существующие по имени, затем через bulk_create создать отсутствующие. Это означает, что любая строка, переданная в `assign_role('superadmin')`, вставит новую роль 'superadmin' в базу данных, если она ещё не существует, и немедленно прикрепит её к модели. Любой вызывающий, способный использовать эти методы — в том числе через API-эндпоинт, передающий пользовательский ввод — может эскалировать привилегии себе или другому пользователю, изобретая имена ролей и прав, которых ранее не существовало.

```python
missing = [n for n in names if n not in existing_names]
if missing:
    await Role.bulk_create(
        [Role(name=n) for n in missing],
        ignore_conflicts=True,
    )
```

**Рекомендация:**
Полностью удалить логику автосоздания. Требовать, чтобы роли и права предварительно создавались администратором. Выбрасывать `ValueError` (или доменное исключение), если запрошенное имя не существует в базе данных. Если автосоздание необходимо для сценариев первичного заполнения, обернуть его в явный флаг `create_if_missing: bool = False` и никогда не вызывать на горячем пути, управляемом пользовательским вводом.

---

### [CRITICAL] Race Condition — sync_permissions и sync_roles неатомарны (TOCTOU) — конкурентные запросы могут повредить состояние прав

**Файл:** permissions/mixins.py:131-136, permissions/mixins.py:207-212
**Серьёзность:** Критическая

**Описание:**
`sync_permissions` сначала выполняет DELETE всех строк `ModelHasPermission` для сущности, затем вызывает `give_permission`, которая выполняет INSERT. В промежутке между DELETE и INSERT существует окно, когда у пользователя нет вообще никаких прав, и любой конкурентный запрос увидит пустой набор прав. При высоком параллелизме два одновременных вызова `sync_permissions` могут также чередоваться, создавая итоговое состояние, которое ни один из вызывающих не предполагал. Та же проблема существует в `sync_roles`.

```python
async def sync_permissions(self, permissions: list[str]) -> None:
    await ModelHasPermission.filter(
        model_type=self._model_type,
        model_id=self.pk,
    ).delete()          # окно открывается здесь
    await self.give_permission(*permissions)   # окно закрывается здесь
```

**Рекомендация:**
Обернуть обе операции в единую транзакцию базы данных с помощью `async with tortoise.transactions.in_transaction()`. Для баз данных, поддерживающих это (PostgreSQL), использовать `SELECT ... FOR UPDATE` на строке сущности для сериализации конкурентных вызовов sync на одного пользователя.

---

### [HIGH] Performance - No Caching — каждый аутентифицированный запрос выполняет 2–3 последовательных обращения к БД без кэша

**Файл:** permissions/dependencies.py:27-43, permissions/mixins.py:41-63
**Серьёзность:** Высокая

**Описание:**
Для каждого защищённого эндпоинта `RequirePermission` и `RequireRole` выполняют: (1) получение пользователя из БД по id, (2) вызов `can()` или `has_role()`, который выполняет ещё 2 запроса (EXISTS по прямым правам и VALUES_LIST по role_id + ещё один EXISTS). Итого минимум 3 последовательных запроса к БД на каждый запрос, без распараллеливания. Графы прав читаются несравнимо чаще, чем записываются, однако TTL-кэш (локальный dict, Redis или иной) для разрешённого набора прав отсутствует.

```python
db_user = await UserModel.get_or_none(id=user_id)   # запрос 1
...
await db_user.can(*permissions)                      # запросы 2 и 3 внутри
```

**Рекомендация:**
Кэшировать разрешённый набор прав и ролей по ключу `(model_type, model_id)` с коротким TTL (например, 30–60 секунд) с помощью `cachetools.TTLCache` в памяти процесса или Redis-хэша. Инвалидировать кэш при каждой записи в `ModelHasPermission` и `ModelHasRole`. Дополнительно распараллелить два внутренних запроса в `can()` с помощью `asyncio.gather`.

---

### [HIGH] Performance - Duplicate DB Queries — can() запрашивает role_ids отдельным запросом вместо одного JOIN, get_all_permissions() дублирует этот паттерн

**Файл:** permissions/mixins.py:41-63, permissions/mixins.py:73-95
**Серьёзность:** Высокая

**Описание:**
`can()` выполняет два обращения к БД: один EXISTS для прямых прав и один VALUES_LIST для role_ids (затем ещё один EXISTS). Все три можно свернуть в единый SQL-запрос с UNION или подзапросом. `get_all_permissions()` также дублирует получение `role_ids`, которое уже выполняет `can()`, поэтому вызывающие, например `has_all_permissions`, платят за это дважды.

```python
role_ids = await ModelHasRole.filter(
    model_type=self._model_type,
    model_id=self.pk,
).values_list("role_id", flat=True)

if role_ids:
    return await Permission.filter(
        name__in=names,
        roles__id__in=list(role_ids),
    ).exists()
```

**Рекомендация:**
Переписать как единый SQL UNION-запрос или использовать raw SQL EXISTS с подзапросом. Как минимум, запускать проверку прямых прав и получение role_id конкурентно с помощью `asyncio.gather`, чтобы вдвое сократить задержку без реструктуризации ORM-вызовов.

---

### [HIGH] Security - Logic Bug / Bypass — has_all_roles возвращает False при дублирующихся именах ролей, даже когда пользователь обладает всеми уникальными ролями

**Файл:** permissions/mixins.py:151-165
**Серьёзность:** Высокая

**Описание:**
`has_all_roles` сравнивает `len(requested_ids) != len(roles)`, где `roles` — это исходный входной кортеж. Если вызывающий передаёт `('admin', 'admin')`, имя роли преобразуется в один DB-идентификатор, поэтому `len(requested_ids)` равен 1, а `len(roles)` равен 2 — функция вернёт `False`, хотя пользователь обладает ролью 'admin'. Это баг корректности, а также незначительная проблема безопасности: если фреймворк или middleware когда-либо формирует списки ролей программно из пользовательского ввода, дублирующаяся запись может обойти обязательную проверку ролей.

```python
requested_ids = set(
    await Role.filter(name__in=list(roles)).values_list("id", flat=True)
)
if len(requested_ids) != len(roles):   # падает, если вызывающий передаёт дубликаты
    return False
```

**Рекомендация:**
Дедуплицировать входные данные перед сравнением: `roles_dedup = list(dict.fromkeys(roles))` и использовать `len(requested_ids) != len(roles_dedup)`.

---

### [HIGH] Security - Missing Guard Filtering — поле guard хранится, но никогда не используется в RBAC-проверках — межстражевое загрязнение прав

**Файл:** permissions/models.py:8,25, permissions/mixins.py:41-63, permissions/mixins.py:140-149
**Серьёзность:** Высокая

**Описание:**
И `Permission`, и `Role` содержат столбец `guard` (по умолчанию 'api'), который в Spatie-стиле RBAC предназначен для изоляции прав по стражу аутентификации (например, 'web' или 'api'). Однако ни один из методов запросов (`can`, `has_role`, `has_all_permissions` и т.д.) никогда не фильтрует по `guard`. Право или роль, созданные для одного стража, удовлетворяют проверкам, предназначенным для другого, создавая путь эскалации межстражевых привилегий.

```python
class Permission(Model):
    guard = fields.CharField(max_length=100, default="api")
    ...
# Позднее в can():
await ModelHasPermission.filter(
    model_type=self._model_type,
    model_id=self.pk,
    permission__name__in=names,
    # guard никогда не проверяется
).exists()
```

**Рекомендация:**
Добавить параметр `guard` (по умолчанию 'api') во все методы проверки и включить `permission__guard=guard` / `role__guard=guard` в каждый ORM-фильтр. Либо явно задокументировать, что guards носят косметический характер, и удалить столбец, чтобы не вводить в заблуждение будущих разработчиков.

---

### [HIGH] Security - Information Leakage — ответы 403 перечисляют точные имена прав и ролей, которых не хватает пользователю

**Файл:** permissions/dependencies.py:37-40, permissions/dependencies.py:72-75
**Серьёзность:** Высокая

**Описание:**
Строки в HTTP 403 `f"Missing permission: {', '.join(permissions)}"` и `f"Required role: {', '.join(roles)}"` раскрывают внутреннюю схему именования прав и ролей любому клиенту, получившему 403. Это помогает атакующим понять модель авторизации и составить целенаправленные попытки эскалации привилегий.

```python
raise HTTPException(
    status_code=403,
    detail=f"Missing permission: {', '.join(permissions)}",
)
```

**Рекомендация:**
Заменить на универсальное сообщение, например `"Forbidden"` или `"Insufficient privileges"`. Если детальные ошибки нужны для отладки, логировать их на уровне WARNING на стороне сервера, но не включать в тело HTTP-ответа.

---

### [MEDIUM] Security - Authorization Gap — RequirePermission и RequireRole не проверяют соответствие аутентифицированного токена полям идентификации пользователя в БД

**Файл:** permissions/dependencies.py:27-43, permissions/dependencies.py:62-78
**Серьёзность:** Средняя

**Описание:**
`CurrentUser` — это Pydantic-модель `AuthUser`, у которой поле `id` типизировано как `Any`. Зависимость только приводит `auth_user.id` к `int` и ищет пользователя в БД по этому PK. Никакие другие идентификационные утверждения (например, email, username, auth_method) не перекрёстно проверяются. Если JWT или cookie подделан или воспроизведён с валидным числовым `sub` от удалённого/заблокированного пользователя, `UserModel.get_or_none` вернёт текущую запись БД по этому PK без какой-либо проверки статуса аккаунта.

```python
db_user = await UserModel.get_or_none(id=user_id)
if not db_user:
    raise HTTPException(status_code=401, detail="User not found")
# Нет проверки is_active, is_banned, email_verified и т.д.
```

**Рекомендация:**
После получения `db_user` проверить, что аккаунт активен и не заблокирован (например, `if not db_user.is_active: raise HTTPException(401)`). Рассмотреть также проверку вторичного утверждения из токена (например, `jti` или `email`) относительно записи в БД для обнаружения повторного использования токена после изменений аккаунта.

---

### [MEDIUM] Race Condition — give_permission и assign_role имеют TOCTOU между bulk_create и последующим SELECT

**Файл:** permissions/mixins.py:99-120, permissions/mixins.py:175-196
**Серьёзность:** Средняя

**Описание:**
Паттерн такой: SELECT существующих имён → вычислить отсутствующие → bulk_create отсутствующие с `ignore_conflicts=True` → SELECT снова для получения всех PK. Между первым SELECT и bulk_create другая конкурентная корутина могла вставить те же самые имена. Поскольку `ignore_conflicts=True` подавляет ошибку дубликата ключа, это безопасно с точки зрения ошибок БД, однако второй SELECT может не вернуть строки, созданные конкурентным писателем, если уровень изоляции транзакций READ COMMITTED и пул соединений раздаёт разные соединения. Список PK, используемый для `ModelHasPermission.bulk_create`, может оказаться неполным.

```python
existing = await Permission.filter(name__in=names).all()  # SELECT 1
...
await Permission.bulk_create([Permission(name=n) for n in missing],
    ignore_conflicts=True)
existing = await Permission.filter(name__in=names).all()  # SELECT 2 — может пропустить строки
```

**Рекомендация:**
Использовать единый raw-запрос `INSERT ... ON CONFLICT DO NOTHING RETURNING *` (PostgreSQL) или обернуть операцию в сериализуемую транзакцию. В более простом ORM-подходе заменить двухфазный SELECT/INSERT на вызов `get_or_create` внутри `asyncio.gather`-разветвления или использовать `RETURNING` для получения PK прямо из INSERT.

---

### [MEDIUM] Performance - Redundant Query — get_all_permissions выполняет избыточный запрос ModelHasRole, те же данные уже получены в can()

**Файл:** permissions/mixins.py:73-95
**Серьёзность:** Средняя

**Описание:**
`has_all_permissions` вызывает `get_all_permissions()`, который выполняет 2 запроса. Но `can()` также выполняет до 3 запросов для частично перекрывающихся данных. Когда оба вызываются в одном контексте запроса (например, middleware, который сначала вызывает `can`, а затем `has_all_permissions` для аудита), получение `role_ids` повторяется. Отсутствует общий контекст или мемоизация на уровне запроса.

```python
async def has_all_permissions(self, *permissions: str) -> bool:
    all_perms = set(await self.get_all_permissions())  # 2 запроса к БД
    return set(permissions).issubset(all_perms)
```

**Рекомендация:**
Реализовать кэш прав на уровне запроса или объекта: после первого вызова `get_all_permissions()` сохранять результат на экземпляре (например, `self.__dict__['_permission_cache'] = result`) и возвращать его при последующих вызовах в течение жизненного цикла одного запроса. Очищать кэш в `give_permission`, `revoke_permission`, `sync_permissions`.

---

### [MEDIUM] Security - Global Singleton Risk — _user_model является модульным глобалом, небезопасным для многоприложных или изолированных тестовых сценариев

**Файл:** permissions/registry.py:8-14
**Серьёзность:** Средняя

**Описание:**
`_user_model` — это голый модульный глобал типа `Optional[Type]`. В Python модульные глобалы общие для всего процесса. Если один процесс запускает несколько FastAPI-приложений (например, во время тестов или в многотенантной конфигурации), последний вызов `setup_permissions(UserModel)` побеждает для всех приложений. Это может молча привести к тому, что проверки прав одного приложения будут запрашивать неправильную модель, потенциально нарушая тенантные границы.

```python
_user_model: Optional[Type] = None

def setup_permissions(user_model: Type) -> None:
    global _user_model
    _user_model = user_model
```

**Рекомендация:**
Привязать реестр к экземпляру FastAPI `app` с помощью `app.state.user_model` вместо модульного глобала. Получать его внутри `_check` через `request.app.state.user_model` (что требует передачи `request` в зависимость, уже доступную через `auth_user: CurrentUser`, который активирует `Request`).

---

### [MEDIUM] Type Safety — AuthUser.id типизирован как Any — приведение int() в dependencies может вызывать исключение на нечисловых значениях id без описательной ошибки

**Файл:** permissions/dependencies.py:29-32, forgeapi/auth/models.py:6
**Серьёзность:** Средняя

**Описание:**
`AuthUser.id` типизирован как `Any`. Зависимость защищена `int(auth_user.id)` внутри `try/except (TypeError, ValueError)`. Но если `id` является UUID-строкой, `int('550e...')` вызовет `ValueError`, возвращая универсальный 401 без записи в лог. Тем временем, если `id` уже является `int`, приведение безвредно, но молча принимает 0 или отрицательные значения, которые не являются валидными PK.

```python
try:
    user_id = int(auth_user.id)
except (TypeError, ValueError):
    raise HTTPException(status_code=401, detail="Invalid user identity")
```

**Рекомендация:**
Логировать исключение на уровне WARNING перед повторным выбросом, чтобы аномальные токены были видны в журнале аудита. Добавить проверку `user_id > 0`. Рассмотреть ужесточение типа `AuthUser.id` до `Union[int, str]` и использование стратегически-специфичного приведения вместо голого `int()`.

---

### [LOW] Code Style - Naming Convention — RequirePermission и RequireRole являются фабричными функциями с именами в PascalCase, что вводит в заблуждение как имена классов

**Файл:** permissions/dependencies.py:11, permissions/dependencies.py:46
**Серьёзность:** Низкая

**Описание:**
PEP 8 резервирует PascalCase для определений классов. `RequirePermission(...)` и `RequireRole(...)` — обычные функции, возвращающие `Depends(...)`. Именование в PascalCase заставляет IDE и линтеры воспринимать их как конструкторы классов, подавляет предупреждения тайп-чекера об отсутствующих типах возврата и сбивает с толку участников, незнакомых с кодовой базой.

```python
def RequirePermission(*permissions: str):
    async def _check(auth_user: CurrentUser):
        ...
    return Depends(_check)
```

**Рекомендация:**
Переименовать в `require_permission` / `require_role` в соответствии с PEP 8. Если PascalCase намеренно используется для имитации эргономики FastAPI `Depends`, добавить комментарий с объяснением соглашения и подавление `# noqa: N802`.

---

### [LOW] Code Style - Missing Return Type Annotations — with_role, without_role и замыкания _check лишены аннотаций возвращаемого типа

**Файл:** permissions/mixins.py:217-232, permissions/dependencies.py:27, permissions/dependencies.py:62
**Серьёзность:** Низкая

**Описание:**
`with_role` и `without_role` объявлены как `async def ... :` без типа возврата. Они возвращают Tortoise `QuerySet`, но вызывающие не имеют никакой типовой информации, что делает невозможной валидацию последующих вызовов `.filter()` или `.all()` тайп-чекерами. Замыкания `_check` в `dependencies.py` также не аннотированы.

```python
@classmethod
async def with_role(cls, *roles: str):   # отсутствует -> QuerySet[Self]
    ...

async def _check(auth_user: CurrentUser):  # отсутствует -> Model
    ...
```

**Рекомендация:**
Добавить аннотации возврата: `-> QuerySet[Self]` для `with_role`/`without_role` и `-> Model` (или конкретный тип модели через `TypeVar`) для замыканий `_check`. Использовать `from __future__ import annotations`, если необходимы опережающие ссылки.

---
