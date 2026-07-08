# Аудит: Auth модуль

## Краткое резюме

Auth-модуль ForgeAPI в целом хорошо структурирован: присутствует дисциплина логирования и корректное использование `hmac.compare_digest` для сравнения за постоянное время. Тем не менее выявлено 21 находок с уровнями от критического до низкого.

Два наиболее срочных вопроса: (1) `JWTStrategy` принимает любую строку алгоритма, включая `'none'`, что открывает атаки на подмену алгоритма; (2) `AuthUser.extra` использует изменяемый литерал `dict` в качестве дефолтного значения Pydantic, что создаёт риск разделения состояния между экземплярами.

Находки высокой серьёзности: дефолтное значение `secure=False` в стратегии Cookie приводит к тому, что сессионные куки передаются в незащищённом виде в продакшне; проверка HMAC для нескольких токенов в Telegram использует `any()` с коротким замыканием, что раскрывает позицию совпавшего ключа через тайминг; `decode()` напрямую поднимает `HTTPException`, связывая JWT-логику с HTTP-слоем.

Находки средней серьёзности: отсутствуют лог-записи в ряде обработчиков исключений, некорректная аннотация возвращаемого типа (`-> type`) у `current_user()`/`optional_user()`, синтаксис union из Python 3.10+ ломает совместимость с 3.8/3.9, а `delete_cookie()` не передаёт атрибуты куки.

Находки низкой серьёзности: молчащий no-op метод `blacklist()` (потенциальная ловушка безопасности), отсутствие серверной проверки времени жизни в сессионных куки, и разбросанные отложенные импорты `HTTPException`, которые должны быть на уровне модуля.

## Находки

### [CRITICAL] [Security] — JWT algorithm not validated — algorithm confusion attack possible

**Файл:** auth/strategies/jwt.py:128
**Серьёзность:** Critical

**Описание:**
`jwt.decode()` вызывается с `algorithms=[self._algorithm]`, где `self._algorithm` — параметр конструктора, по умолчанию равный `'HS256'`, однако никогда не валидируется по списку допустимых значений. Оператор может передать `algorithm='none'` или `algorithm='RS256'` (с публичным ключом в качестве секрета). PyJWT принимает `'none'`, если он явно передан в списке алгоритмов, полностью обходя проверку подписи. Конструктор принимает любую произвольную строку без валидации.

```python
return jwt.decode(token, self._secret, algorithms=[self._algorithm])
```

**Рекомендация:**
Определить явный список допустимых алгоритмов, например `ALLOWED_ALGORITHMS = {'HS256', 'HS384', 'HS512'}`, и валидировать `algorithm` по нему в `__init__` перед присвоением. Поднимать `ForgeAPIConfigError`, если значение выходит за пределы списка. Никогда не допускать `'none'` или асимметричные алгоритмы, если стратегия основана на секретном ключе (HMAC).

---

### [CRITICAL] [Security] — Mutable default argument on AuthUser.extra creates shared state across instances

**Файл:** auth/models.py:8
**Серьёзность:** Critical

**Описание:**
Поле Pydantic-модели `extra: dict = {}` использует голый изменяемый литерал `dict` в качестве дефолтного значения. В Pydantic v1 это дефолт уровня класса, и Pydantic копирует его на каждый экземпляр, однако в Pydantic v2 поведение изменилось: при отсутствии `Field()` один и тот же объект `dict` может быть общим. Даже в v1 это известный анти-паттерн Python, ведущий к неочевидной утечке данных между запросами, если не-Pydantic подкласс или датакласс унаследует эту модель. Корректная форма — `Field(default_factory=dict)`.

```python
extra: dict = {}
```

**Рекомендация:**
Использовать `extra: dict = Field(default_factory=dict)` и импортировать `Field` из `pydantic`. Это корректно как для Pydantic v1, так и для v2, и полностью устраняет риск разделения состояния.

---

### [HIGH] [Security] — CookieStrategy: secure=False is the default — session cookies sent over plain HTTP in production

**Файл:** auth/strategies/cookie.py:60
**Серьёзность:** High

**Описание:**
Параметр `secure` по умолчанию равен `False`, что означает: сессионные куки передаются без флага `Secure`. Хотя предупреждение логируется, дефолт неверный для библиотеки, используемой в веб-API. Разработчик, не читающий логи или документацию, выпустит небезопасную конфигурацию по умолчанию. Куки без `Secure` могут быть перехвачены по любому HTTP-соединению.

```python
secure: bool = False,
```

**Рекомендация:**
Изменить дефолт на `secure=True`. Если необходима разработка по HTTP, явно задокументировать переопределение. В качестве альтернативы — определять схему входящего запроса и логировать предупреждение высокой серьёзности на уровне запроса, а не молчаливо устанавливать небезопасный дефолт.

---

### [HIGH] [Security] — Telegram HMAC comparison performed before auth_date expiry check — timing oracle on expired tokens

**Файл:** auth/strategies/telegram.py:109-132
**Серьёзность:** High

**Описание:**
Проверка HMAC выполняется через `any(hmac.compare_digest(...) for key in self._secret_keys)`. Генератор Python с `any()` завершается при первом результате `True`, то есть количество выполненных HMAC-операций (и, следовательно, тайминг) зависит от того, на какой позиции находится совпавший ключ. Для одного токена это приемлемо, но для мульти-токенного сценария утечка позиции позволяет злоумышленнику перечислить, какой бот-токен активен.

```python
valid = any(
    hmac.compare_digest(
        hmac.new(key, data_check.encode(), hashlib.sha256).hexdigest(),
        received_hash,
    )
    for key in self._secret_keys
)
```

**Рекомендация:**
Вычислить все HMAC-дайджесты безусловно (без короткого замыкания), затем объединить результаты через OR: `results = [hmac.compare_digest(hmac.new(k, data_check.encode(), hashlib.sha256).hexdigest(), received_hash) for k in self._secret_keys]; valid = any(results)`. Это предотвращает утечку тайминга позиции совпавшего ключа.

---

### [HIGH] [Security] — JWT token type claim checked after decode but type field is user-controlled at issuance

**Файл:** auth/strategies/jwt.py:165
**Серьёзность:** High

**Описание:**
Поле `type` в payload записывается `create_access_token`/`create_refresh_token` и проверяется в `authenticate`, чтобы не допустить использование refresh-токенов как access-токенов. Однако `decode()` — публичный метод, не проверяющий наличие клейма `type` в декодируемом токене из сторонней системы. Реальная проблема в том, что два экземпляра `JWTStrategy` с разными назначениями (access vs refresh) успешно декодируют токены друг друга через `decode()` без ошибки — только `authenticate()` проверяет `type`, а `decode()` молча возвращает payload refresh-токена.

```python
payload = self.decode(credentials.credentials)
if payload.get("type") != "access":
```

**Рекомендация:**
Добавить опциональный параметр `expected_type` в `decode()`, чтобы вызывающий код мог принудить тип токена на этапе декодирования. В качестве альтернативы — явно задокументировать, что `decode()` является низкоуровневым методом, а валидация типа — ответственность вызывающего. Рассмотреть использование зарегистрированного клейма, например кастомного `aud` (audience), вместо свободного текстового поля `type`.

---

### [HIGH] [Security] — Cookie _verify swallows all exceptions during base64/JSON decode with no logging

**Файл:** auth/strategies/cookie.py:183-186
**Серьёзность:** High

**Описание:**
Голый `except Exception` на строке 185 перехватывает любую ошибку при base64-декодировании и JSON-парсинге, но не логирует её. Это скрывает неожиданные ошибки (например, `UnicodeDecodeError`, `OverflowError` на некорректных данных), делая невозможным разграничение реальной атаки от бага в коде в продакшне. Кроме того, `HTTPException` с фиксированной строкой `detail` раскрывает внутреннее устройство (`'Invalid session cookie payload'`), что может помочь злоумышленнику понять формат куки.

```python
try:
    return json.loads(base64.urlsafe_b64decode(payload + "==").decode())
except Exception:
    raise HTTPException(status_code=401, detail="Invalid session cookie payload")
```

**Рекомендация:**
Перехватывать конкретные исключения (`json.JSONDecodeError`, `UnicodeDecodeError`, `binascii.Error`) вместо голого `Exception`. Добавить вызов `logger.warning()` с деталями исключения перед повторным поднятием. Использовать обобщённую строку `detail`, например `'Invalid session'`, чтобы не раскрывать детали реализации.

---

### [HIGH] [Type Safety] — AuthUser.id typed as Any — downstream code receives untyped user identity

**Файл:** auth/models.py:6
**Серьёзность:** High

**Описание:**
Поле `id` у `AuthUser` типизировано как `Any`. Это означает, что весь нижестоящий код (обработчики маршрутов, бизнес-логика), читающий `user.id`, получает нетипизированное значение. JWT-стратегия передаёт строку (`payload['sub']` всегда `str`), Telegram-стратегия передаёт целое число (`tg_id`), а Cookie-стратегия передаёт всё, что хранится в JSON. Несогласованность означает, что тайп-чекеры не могут поймать баги. В Telegram `AuthUser.id` устанавливается как `int`, тогда как в JWT — как `str`: несовместимые типы для одного и того же поля.

```python
class AuthUser(BaseModel):
    id: Any
```

**Рекомендация:**
Использовать тип-объединение: `id: Union[str, int]` или принудительно приводить к строке на каждом месте создания в стратегиях — `str(tg_user.id)` и `str(payload.get('sub'))` перед установкой `AuthUser.id`. Это делает нижестоящий код безопасным по типам и устраняет молчаливое несоответствие `int`/`str` между стратегиями.

---

### [MEDIUM] [Security] — JWT decode() raises HTTPException — inappropriate coupling of transport error to library method

**Файл:** auth/strategies/jwt.py:129-136
**Серьёзность:** Medium

**Описание:**
`decode()` — публичный метод, который напрямую поднимает `fastapi.HTTPException`. Это связывает JWT-логику с HTTP-транспортным слоем, делая `decode()` неприменимым в фоновых задачах, CLI-инструментах, Celery-воркерах или WebSocket-обработчиках, где `HTTPException` не имеет смысла. Любой код, вызывающий `decode()` вне контекста HTTP-запроса, получит специфичное для фреймворка исключение, которое может остаться неперехваченным.

```python
except jwt.ExpiredSignatureError:
    from fastapi import HTTPException
    logger.debug("JWT decode failed: token expired")
    raise HTTPException(status_code=401, detail="Token has expired")
except jwt.InvalidTokenError:
    from fastapi import HTTPException
    logger.debug("JWT decode failed: invalid token")
    raise HTTPException(status_code=401, detail="Invalid token")
```

**Рекомендация:**
Поднимать доменные исключения из `decode()` (например, `TokenExpiredError`, `TokenInvalidError`, наследующие от базового `ForgeAPIAuthError`). Пусть `authenticate()` перехватывает их и преобразует в `HTTPException`. Это сохраняет переиспользуемость стратегии вне FastAPI и следует принципу разделения ответственности.

---

### [MEDIUM] [Security] — Telegram: Authorization header slice is off-by-one for 'tma ' prefix

**Файл:** auth/strategies/telegram.py:196-197
**Серьёзность:** Medium

**Описание:**
При извлечении `init_data` из заголовка `Authorization` код использует `auth[4:]` после проверки `auth.lower().startswith('tma ')`. Реальная проблема: отсутствует вызов `strip()`, поэтому `Authorization: tma  <data>` (двойной пробел) пройдёт проверку `startswith`, но в возвращаемом `init_data` будет присутствовать ведущий пробел, что приведёт к молчаливой ошибке валидации HMAC.

```python
if auth.lower().startswith("tma "):
    return auth[4:]
```

**Рекомендация:**
Использовать `auth[4:].strip()` или `auth[len('tma '):].strip()`, чтобы обрезать случайные пробелы из извлечённого значения `init_data`. Также рекомендуется задокументировать, что значение заголовка должно использовать единственный пробел в качестве разделителя префикса.

---

### [MEDIUM] [Security] — CookieStrategy.delete_cookie does not pass matching cookie attributes — cookie may not be deleted

**Файл:** auth/strategies/cookie.py:137
**Серьёзность:** Medium

**Описание:**
`response.delete_cookie(self._cookie_name)` вызывается без передачи атрибутов `path`, `domain`, `secure` или `samesite`. RFC 6265 требует, чтобы заголовок `Set-Cookie` с `Max-Age=0` совпадал с атрибутами `path` и `domain` исходной куки для её удаления. Если кука была установлена с нестандартным `path` или `domain`, вызов `delete_cookie` без этих атрибутов может привести к созданию новой куки (или молчаливому провалу удаления) вместо удаления исходной.

```python
response.delete_cookie(self._cookie_name)
```

**Рекомендация:**
Передавать все соответствующие атрибуты куки при удалении: `response.delete_cookie(self._cookie_name, path='/', httponly=self._httponly, secure=self._secure, samesite=self._samesite)`. Хранить `path` и `domain` как атрибуты экземпляра, если они настраиваемы.

---

### [MEDIUM] [Code Style] — Dead code: unused variable 'reserved' defined but never read in authenticate()

**Файл:** auth/strategies/jwt.py:169
**Серьёзность:** Medium

**Описание:**
Переменная `reserved` определяется в середине функции, что делает её визуально похожей на мёртвый код, хотя на самом деле используется в следующей строке. Это чисто стилистическая проблема — переменную следует вынести на уровень класса или в начало метода.

```python
reserved = {"sub", "username", "exp", "iat", "type"}
logger.debug("JWT auth OK: user_id=%s", payload.get("sub"))

return AuthUser(
    id=payload.get("sub"),
    username=payload.get("username"),
    extra={k: v for k, v in payload.items() if k not in reserved},
```

**Рекомендация:**
Перенести `reserved` на уровень класса как константу `frozenset`: `_RESERVED_CLAIMS: frozenset[str] = frozenset({'sub', 'username', 'exp', 'iat', 'type'})`. Это наглядно, избегает пересоздания множества на каждый запрос и допускает повторное использование при расширении `decode()`.

---

### [MEDIUM] [Code Style] — AuthBackend.current_user() and optional_user() return type annotated as 'type' — incorrect and misleading

**Файл:** auth/backend.py:121
**Серьёзность:** Medium

**Описание:**
Оба метода `current_user()` и `optional_user()` аннотированы как возвращающие `type`, но фактически возвращают дженерик-алиас `Annotated[...]`, который не является экземпляром `type` в системе типов Python. Это означает, что mypy и pyright будут отмечать ошибки в любом коде, который пытается использовать возвращаемое значение как аннотацию типа.

```python
def current_user(self) -> type:
def optional_user(self) -> type:
```

**Рекомендация:**
Аннотировать оба метода как возвращающие `Any` (с поясняющим комментарием) или использовать `TypeAlias`. В Python 3.12+ можно использовать `type[Any]`. Импортировать `Any` из `typing` и использовать: `def current_user(self) -> Any:` с докстрингом, объясняющим, что возврат является аннотированным псевдонимом типа для использования в зависимостях FastAPI.

---

### [MEDIUM] [Type Safety] — TelegramStrategy.__init__ uses Python 3.10+ union syntax in a file that may target 3.8/3.9

**Файл:** auth/strategies/telegram.py:54
**Серьёзность:** Medium

**Описание:**
Сигнатура конструктора использует `str | list[str]`, что допустимо только в Python 3.10+. Остальная кодовая база использует `from typing import Optional` (старая форма), что предполагает поддержку Python 3.8 или 3.9. Использование нового синтаксиса union в позиции аннотации типа вызовет `TypeError` при определении класса на Python 3.9 и ниже (не только на этапе проверки типов, поскольку это не строковая аннотация).

```python
def __init__(self, bot_token: str | list[str], max_age_seconds: Optional[int] = 86400, debug: bool = False) -> None:
```

**Рекомендация:**
Заменить `str | list[str]` на `Union[str, List[str]]` из `typing`, или добавить `from __future__ import annotations` в начало файла для отложенного вычисления аннотаций. Это обеспечит совместимость с Python 3.8 и 3.9. Проверить минимальную версию Python в `pyproject.toml` и применить единообразно во всём модуле.

---

### [MEDIUM] [Exception Handling] — ValueError from int(params.get('auth_date', 0)) not logged before re-raise

**Файл:** auth/strategies/telegram.py:105-108
**Серьёзность:** Medium

**Описание:**
`ValueError`, перехватываемый при парсинге `auth_date`, молча проглатывается — лог-запись не производится перед поднятием `HTTPException`. Это делает невозможным разграничение легитимного клиента, отправляющего некорректный timestamp, от злоумышленника, зондирующего endpoint. Все пути отклонения аутентификации должны логироваться на уровне warning с достаточным контекстом для построения правил алертинга.

```python
try:
    auth_date = int(params.get("auth_date", 0))
except ValueError:
    raise HTTPException(status_code=401, detail="Invalid auth_date in Telegram init data")
```

**Рекомендация:**
Добавить `logger.warning('Telegram auth rejected: invalid auth_date value: %r', params.get('auth_date'))` перед поднятием `HTTPException`, в соответствии с другими путями отклонения в том же методе.

---

### [MEDIUM] [Exception Handling] — Malformed Telegram user JSON field not logged before re-raise

**Файл:** auth/strategies/telegram.py:139-142
**Серьёзность:** Medium

**Описание:**
Блок `except` для `json.JSONDecodeError` / `ValueError` при парсинге JSON-поля `user` поднимает `HTTPException` без логирования. Это несогласованно с остальной частью метода, где все другие пути отклонения логируются на уровне warning.

```python
except (json.JSONDecodeError, ValueError):
    raise HTTPException(status_code=401, detail="Malformed user field in Telegram init data")
```

**Рекомендация:**
Добавить `logger.warning('Telegram auth rejected: malformed user JSON field: %r', user_raw)` перед поднятием. При необходимости обрезать `user_raw` в логе, если значение может быть большим, чтобы избежать log injection.

---

### [MEDIUM] [Security] — Global backend singleton has no thread/async safety guard during set_global_backend

**Файл:** auth/backend.py:65-81
**Серьёзность:** Medium

**Описание:**
`set_global_backend()` выполняет присвоение глобальной переменной без какой-либо блокировки. В многопоточной или многопроцессной среде (например, gunicorn с синхронными воркерами или startup-хук, срабатывающий параллельно) два вызова `set_global_backend()` могут вступить в гонку. Функции `_global_current_user()` и `_global_optional_user()` читают `_global_backend` без блокировки, что означает возможность увидеть частично построенное или устаревшее значение в многопоточном контексте.

```python
def set_global_backend(backend: "AuthBackend") -> None:
    global _global_backend
    _global_backend = backend
```

**Рекомендация:**
Задокументировать, что `set_global_backend()` должен вызываться ровно один раз при старте приложения, до того как начнут обрабатываться запросы. Для повышения надёжности рассмотреть использование `threading.Lock` или `asyncio.Lock` вокруг присвоения и чтения, либо использовать паттерн с sentinel на уровне модуля, который поднимает ошибку при повторном вызове после первого запроса.

---

### [LOW] [Code Style] — Inconsistent logging level for JWT decode failures — debug vs warning

**Файл:** auth/strategies/jwt.py:131
**Серьёзность:** Low

**Описание:**
Истечение срока токена и неверная подпись логируются на уровне DEBUG. Истёкшие токены — ожидаемое событие (короткоживущие токены нормально истекают), однако неверная подпись — потенциальное событие безопасности (поддельный токен, неверный секрет, несоответствие алгоритма) и должна логироваться на уровне WARNING для мониторинга безопасности. Стратегии Cookie и Telegram логируют несоответствия подписей на уровне WARNING, создавая несогласованность.

```python
except jwt.ExpiredSignatureError:
    logger.debug("JWT decode failed: token expired")
except jwt.InvalidTokenError:
    logger.debug("JWT decode failed: invalid token")
```

**Рекомендация:**
Оставить `ExpiredSignatureError` на уровне DEBUG (штатное операционное событие). Повысить `InvalidTokenError` (кроме истечения срока) до WARNING: `logger.warning('JWT decode failed: invalid token signature or structure')`. Это согласуется со стратегиями Cookie и Telegram.

---

### [LOW] [Code Style] — HTTPException imported inside except blocks and if branches instead of at module top level

**Файл:** auth/strategies/jwt.py:130,134,166
**Серьёзность:** Low

**Описание:**
`fastapi.HTTPException` импортируется внутри нескольких блоков `except` и условных ветвей по всему `jwt.py`. Такой же паттерн присутствует в `telegram.py` и `cookie.py`. Хотя Python кеширует импорты модулей после первого вызова, повторяющийся паттерн отложенного импорта сложнее аудировать, скрывает зависимости файла и несогласован — `fastapi.Request` импортируется на верхнем уровне, а `HTTPException` — нет.

```python
except jwt.ExpiredSignatureError:
    from fastapi import HTTPException
    ...
except jwt.InvalidTokenError:
    from fastapi import HTTPException
```

**Рекомендация:**
Перенести `from fastapi import HTTPException` в секцию импортов верхнего уровня каждого файла, рядом с существующим `from fastapi import Request`. Паттерн отложенного импорта необходим только при риске циклического импорта, которого здесь нет.

---

### [LOW] [Code Style] — JWTStrategy._bearer is a class-level attribute shared across all instances

**Файл:** auth/strategies/jwt.py:54
**Серьёзность:** Low

**Описание:**
`_bearer = HTTPBearer(auto_error=False)` определён на уровне класса, что означает совместное использование одного объекта `HTTPBearer` всеми экземплярами `JWTStrategy`. Это преднамеренно для эффективности, но не задокументировано и может вызвать путаницу, если подкласс попытается переопределить схему. Также это означает, что изменение extractor'а bearer для одного экземпляра затронет все экземпляры.

```python
_bearer = HTTPBearer(auto_error=False)
```

**Рекомендация:**
Либо явно задокументировать совместное использование на уровне класса с помощью комментария, либо перенести `_bearer` в `__init__` как `self._bearer = HTTPBearer(auto_error=False)`. Последнее незначительно менее эффективно (один дополнительный объект на экземпляр), но исключает неочевидное разделение состояния.

---

### [LOW] [Type Safety] — AuthUser.extra typed as plain dict with no key/value type parameters

**Файл:** auth/models.py:8
**Серьёзность:** Low

**Описание:**
Поле `extra` типизировано как `dict` без параметров типов (должно быть `dict[str, Any]`). Без параметров типов mypy трактует это как `dict[Any, Any]`, что означает: значения, читаемые из `extra`, имеют тип `Any` и типобезопасность ключей теряется. Все три стратегии записывают строковые ключи в `extra`, поэтому корректный тип — `dict[str, Any]`.

```python
extra: dict = {}
```

**Рекомендация:**
Изменить на `extra: dict[str, Any] = Field(default_factory=dict)` (совместив это с исправлением изменяемого дефолта). Импортировать `Any` из `typing`.

---

### [LOW] [Code Style] — blacklist() method is a no-op with no NotImplementedError or abstract designation

**Файл:** auth/strategies/jwt.py:138-147
**Серьёзность:** Low

**Описание:**
Метод `blacklist()` задокументирован как заглушка, но не помечен как абстрактный или устаревший. Разработчик, вызывающий `auth.blacklist(token)` в ожидании отзыва токена, молча получит успех без ошибки, предупреждения и фактического отзыва. Это потенциальная ловушка безопасности: код, который выглядит как отзыв токенов, ничего не делает.

```python
def blacklist(self, token: str) -> None:
    pass
```

**Рекомендация:**
Либо (а) добавить внутрь `blacklist()` вызов `logger.warning()` со словами "Token blacklisting is not implemented — tokens will remain valid until expiry. Override this method or use a Redis-backed implementation.", либо (б) сделать метод поднимающим `NotImplementedError` по умолчанию и предоставить конкретный `RedisBlacklistMixin`. Как минимум добавить runtime-предупреждение, чтобы no-op был виден в логах.

---

### [LOW] [Security] — Cookie session has no expiry claim — replay attack window is unbounded within max_age

**Файл:** auth/strategies/cookie.py:82-99
**Серьёзность:** Low

**Описание:**
Подписанный cookie-payload содержит только то, что передаёт вызывающий код в `data` — никакого серверного клейма `issued_at` или `expires_at` не добавляется автоматически. Атрибут `max_age` куки применяется браузером, но злоумышленник, перехвативший значение куки, может воспроизводить его бесконечно на стороне сервера (сервер проверяет только HMAC-подпись, но не timestamp). В отличие от JWT с клеймом `exp`, проверяемым на сервере, эта стратегия куки не имеет серверной проверки истечения срока.

```python
def create_session(self, data: dict) -> str:
    payload = base64.urlsafe_b64encode(json.dumps(data).encode()).decode()
    return f"{payload}.{self._sign(payload)}"
```

**Рекомендация:**
Автоматически добавлять timestamp `exp` в данные сессии в `create_session()`: `data = {**data, 'exp': int(time.time()) + self._max_age}`. В `authenticate()`, после проверки HMAC, проверять, что `data.get('exp', 0) > time.time()`, и поднимать `HTTPException 401` при истечении срока. Это обеспечивает серверную проверку срока независимо от времени жизни куки в браузере.

---
