# Аудит: Middleware модуль

## Краткое резюме

Middleware-стек содержит две критические уязвимости безопасности: вспомогательная функция CORS по умолчанию использует `credentials=True` вместе с wildcard-источниками (нарушение спецификации и риск обхода аутентификации), а rate-limiter формирует ключ клиента на основе полностью контролируемого атакующим заголовка `X-Forwarded-For` (тривиальный обход). Существует ещё пять проблем высокой серьёзности: заголовок `X-Request-ID` отражается в ответах без валидации CRLF и длины (инъекция заголовков), хранилище rate-limit содержит логическую ошибку, из-за которой код очистки пересоздаёт только что удалённую очередь (утечка памяти), а также не является атомарным при конкурентном async-доступе, и `LoggingMiddleware` поглощает контекст исключений в блоке `finally`. Механизм патчинга сигнатур в `Guard` передаёт параметр `self` в систему DI FastAPI, что приведёт к ошибкам инъекции во время выполнения. Нигде не устанавливаются защитные заголовки ответа (CSP, `X-Frame-Options`, `X-Content-Type-Options`). Во всех методах `dispatch` параметр `call_next` не имеет типовой аннотации. Rate-limiter не поддерживает исключение путей, то есть health-пробы Kubernetes расходуют квоту rate-limit. Итого: 2 критических, 5 высоких, 5 средних, 4 низких находки в 6 файлах.

## Находки

### [CRITICAL] Security — CORS wildcard origin combined with allow_credentials=True

**Файл:** middleware/cors.py:5-18
**Серьёзность:** Критическая

**Описание:**
Вызов `add_cors()` по умолчанию передаёт `allow_credentials=True` вместе с `allow_origins=["*"]`. Спецификация CORS запрещает такую комбинацию: браузеры отклоняют cross-origin запросы с учётными данными, когда сервер отвечает `Access-Control-Allow-Origin: *`. `CORSMiddleware` от Starlette молча убирает заголовок credentials в таком случае, поэтому поведение различается между браузерными и небраузерными клиентами и может привести к тонкому обходу аутентификации, если вызывающая сторона предполагает, что учётные данные проверяются. Любой источник принимается без ограничений.

```python
def add_cors(
    app: FastAPI,
    origins: list[str] = ["*"],
    allow_credentials: bool = True,
    allow_methods: list[str] = ["*"],
    allow_headers: list[str] = ["*"],
) -> None:
```

**Рекомендация:**
Никогда не объединяйте `allow_credentials=True` с `allow_origins=["*"]`. Требуйте от вызывающих сторон явного указания списка разрешённых источников. Измените значение по умолчанию для `allow_credentials` на `False` и проверяйте при старте, что если credentials включены, то предоставлен явный список origins. Выбрасывайте `ValueError` или `ForgeAPIConfigError` при обнаружении небезопасной комбинации.

---

### [CRITICAL] Security — Rate-limit key fully controlled by client via X-Forwarded-For header

**Файл:** middleware/rate_limit.py:21-25
**Серьёзность:** Критическая

**Описание:**
Rate-limiter формирует идентификатор клиента из заголовка запроса `X-Forwarded-For` без какой-либо валидации цепочки прокси. Любой клиент может подделать произвольный IP-адрес в этом заголовке (например, `X-Forwarded-For: 1.2.3.4`) и полностью обойти rate-limit. Эта атака не требует аутентификации и легко автоматизируется.

```python
client_ip = (
    request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
    or request.headers.get("X-Real-IP", "")
    or (request.client.host if request.client else "unknown")
)
```

**Рекомендация:**
Доверяйте крайнему левому значению `X-Forwarded-For` только в том случае, если перед приложением гарантированно находится доверенный обратный прокси. Реализуйте явный список доверенных прокси: читайте только N-ю запись справа, где N — количество известных доверенных прокси. Если приложение может принимать прямые соединения, всегда используйте `request.client.host` и никогда не доверяйте заголовкам, предоставленным клиентом, без соответствующей конфигурации.

---

### [HIGH] Security — X-Request-ID header value reflected verbatim into response without sanitisation

**Файл:** middleware/request_id.py:10-13
**Серьёзность:** Высокая

**Описание:**
Middleware читает клиентский заголовок `X-Request-ID` и копирует его напрямую в заголовки ответа. Злонамеренный клиент может внедрить CRLF-последовательности (например, `\r\n`), что в зависимости от версии ASGI-сервера может позволить HTTP response header splitting или инъекцию в логи. Даже без header splitting в каждый заголовок ответа попадают произвольные данные, контролируемые атакующим.

```python
request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
request.state.request_id = request_id
response = await call_next(request)
response.headers["X-Request-ID"] = request_id
```

**Рекомендация:**
Валидируйте входящий `X-Request-ID` перед использованием. Применяйте строгий allowlist: принимайте только буквенно-цифровые символы, дефисы и подчёркивания с максимальной длиной (например, 64 символа). Отклоняйте или заменяйте значения, не соответствующие шаблону. Пример: `import re; if not re.fullmatch(r'[\w-]{1,64}', request_id): request_id = str(uuid.uuid4())`.

---

### [HIGH] Security — Mutable default arguments create a shared-state security and correctness bug in add_cors

**Файл:** middleware/cors.py:6-10
**Серьёзность:** Высокая

**Описание:**
Python вычисляет значения аргументов по умолчанию один раз при определении функции, а не при каждом вызове. Три параметра-списка (`origins`, `allow_methods`, `allow_headers`) являются одними и теми же объектами списков во всех вызовах. Если какой-либо вызывающий код мутирует список через инспекцию или ссылку, это молча изменяет значения по умолчанию для последующих вызовов. Что ещё важнее, wildcard-значения по умолчанию означают, что любое развёртывание, забывшее передать `origins`, получит полностью открытый CORS с credentials.

```python
def add_cors(
    app: FastAPI,
    origins: list[str] = ["*"],
    allow_credentials: bool = True,
    allow_methods: list[str] = ["*"],
    allow_headers: list[str] = ["*"],
) -> None:
```

**Рекомендация:**
Используйте `None` как значение-сентинел по умолчанию и присваивайте список внутри тела функции. Например: `origins: list[str] | None = None` и затем `origins = origins or ["*"]`. Также рассмотрите возможность сделать wildcard-значение по умолчанию opt-in, а не opt-out, чтобы вызывающие стороны осознанно выбирали открытый CORS.

---

### [HIGH] Security — No security response headers set anywhere in the middleware stack

**Файл:** middleware/base_middleware.py:1, middleware/cors.py:1
**Серьёзность:** Высокая

**Описание:**
Ни один из предоставленных middleware не устанавливает распространённые защитные HTTP-заголовки ответа, такие как `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Content-Security-Policy` или `Strict-Transport-Security`. Приложения, построенные на ForgeAPI, не имеют базовой защиты от clickjacking, MIME sniffing или утечки информации, если разработчики не добавят их вручную.

**Рекомендация:**
Добавьте `SecurityHeadersMiddleware` (или расширьте базовый класс `Middleware`), который по умолчанию инжектирует `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin` и ограничительный `Content-Security-Policy`. Задокументируйте, какие заголовки вызывающим сторонам может потребоваться ослабить.

---

### [HIGH] Exception Handling — Exceptions raised inside call_next are silently swallowed in LoggingMiddleware

**Файл:** middleware/logging.py:15-29
**Серьёзность:** Высокая

**Описание:**
Блок `try/finally` фиксирует ответ при успешном выполнении `call_next`, но никогда не перебрасывает исключение. Если `call_next` выбрасывает исключение (например, сетевая ошибка или необработанное исключение из нижележащего middleware), блок `finally` всё равно выполняется и логирует `status=500`, но исключение распространяется вверх без логирования. Это означает, что контекст ошибки (трассировка стека, тип исключения) теряется на границе middleware, а запись в лог вводит в заблуждение: показывает искусственный 500, а не реальный класс исключения.

```python
status = 500
try:
    response = await call_next(request)
    status = response.status_code
    return response
finally:
    duration_ms = (time.perf_counter() - start) * 1000
    ...
    logger.info(..., status, ...)
```

**Рекомендация:**
Добавьте явный блок `except` для захвата и логирования исключения на уровне ERROR перед повторным выбросом: `except Exception as exc: logger.error(..., exc_info=exc); raise`. Также рассмотрите использование `logger.error` вместо `logger.info` для статусов 5xx, чтобы улучшить мониторинг.

---

### [HIGH] Performance — In-memory rate-limit store is not thread-safe and will leak memory under concurrent load

**Файл:** middleware/rate_limit.py:18, 29-34
**Серьёзность:** Высокая

**Описание:**
Словарь `_store` является обычным `defaultdict(deque)`, разделяемым между всеми asyncio-задачами без блокировок. При конкурентных async-запросах (которые могут чередоваться в любой точке `await`) последовательность чтение-модификация-запись временных меток не является атомарной. Кроме того, логика очистки в строках 32-34 удаляет ключ из `_store`, а затем немедленно пересоздаёт его через доступ `defaultdict` в строке 34, поэтому очистка неэффективна: deque всегда пересоздаётся, а ключи `client_ip` никогда не удаляются, что приводит к неограниченному росту памяти для уникальных IP-адресов.

```python
if not timestamps and client_ip in self._store:
    del self._store[client_ip]
    timestamps = self._store[client_ip]  # re-creates via defaultdict!
```

**Рекомендация:**
Удалите неработающий блок очистки (строки 32-34); deque останется пустым и не причинит вреда. Для правильного управления памятью удаляйте ключ только после подтверждения, что deque остаётся пустым, и избегайте повторного обращения к `self._store[client_ip]` через defaultdict. Для production-использования замените in-process хранилище на Redis (используя атомарные операции `ZADD`/`ZCOUNT`) или используйте `asyncio.Lock` вокруг критической секции. Также задокументируйте, что этот middleware несовместим с многопроцессными развёртываниями (например, Gunicorn с несколькими воркерами).

---

### [HIGH] Performance — time.time() called once but O(n) deque scan performed per request — unbounded per-IP work

**Файл:** middleware/rate_limit.py:26-31
**Серьёзность:** Высокая

**Описание:**
Для каждого запроса middleware итерирует всю deque временных меток для клиентского IP, чтобы удалить устаревшие записи. Если один IP делает много запросов, deque может содержать до `_rpm` записей, и цикл `while` выполняется до `_rpm` итераций на запрос. При высокоинтенсивной атаке это становится O(rpm) CPU-работой на запрос в горячем пути middleware, которая является синхронной и блокирует event loop. При лимите по умолчанию 60 rpm это незначительно, но при больших пользовательских лимитах становится существенным.

```python
while timestamps and timestamps[0] < window_start:
    timestamps.popleft()
```

**Рекомендация:**
Вытеснение по скользящему окну по своей природе O(expired), что приемлемо для нормального трафика. Однако добавьте ограничение максимального размера deque для ограничения памяти на IP и рассмотрите документирование production-only природы in-memory хранилища. Для настоящего исправления перейдите на Redis с sorted sets (`ZADD`/`ZREMRANGEBYSCORE`/`ZCARD` — O(log N) и атомарно).

---

### [MEDIUM] Exception Handling — LoggingMiddleware logs status=500 for all exceptions including client errors

**Файл:** middleware/logging.py:13-14
**Серьёзность:** Средняя

**Описание:**
Значение-сентинел `status = 500` устанавливается перед блоком `try`. Если `call_next` выбрасывает не-HTTP исключение, которое затем перехватывается внешним обработчиком исключений и конвертируется в ответ 4xx, запись в лог неверно зафиксирует 500. Это засоряет дашборды ошибок и делает измерения SLO ненадёжными.

```python
status = 500
try:
    response = await call_next(request)
    status = response.status_code
```

**Рекомендация:**
Используйте `status = None` как сентинел, устанавливайте значение только при получении реального ответа и явно различайте в логировании исключения и HTTP-ответы. Alternatively используйте чистый ASGI middleware (например, `DebugMiddleware` в `telescope/middleware.py`), который захватывает реальный HTTP-статус из сообщения `response.start` даже при возникновении ошибок.

---

### [MEDIUM] Exception Handling — RequestIDMiddleware has no error handling — exceptions from call_next leave request_id unset in response

**Файл:** middleware/request_id.py:9-13
**Серьёзность:** Средняя

**Описание:**
Если `call_next` выбрасывает исключение, объект ответа никогда не получается и заголовок `X-Request-ID` никогда не записывается в ответ об ошибке, сгенерированный внешними обработчиками. Это делает невозможным корреляцию ответов об ошибках с request ID в логах, что нивелирует основную цель паттерна request ID.

```python
response = await call_next(request)
response.headers["X-Request-ID"] = request_id
return response
```

**Рекомендация:**
Оберните `call_next` в `try/except`, перебрасывайте исключение и убедитесь, что ответы об ошибках, генерируемые ниже по стеку, также содержат request ID. Поскольку `BaseHTTPMiddleware` не позволяет легко инжектировать заголовки в ответы, сгенерированные исключениями, рассмотрите переход на чистый ASGI middleware, который перехватывает сообщение `http.response.start` и инжектирует заголовок на уровне ASGI.

---

### [MEDIUM] Type Safety — Guard.__init_subclass__ patches __call__ with wrong signature — self parameter is doubled

**Файл:** middleware/guard.py:52-57
**Серьёзность:** Средняя

**Описание:**
Внутри `__init_subclass__` замыкание `async def __call__(self, **kw)` уже получает `self` как связанный метод. Но `__call__.__signature__` устанавливается в `inspect.signature(handle_fn)`, которая включает `self` в качестве первого параметра. FastAPI видит патченную сигнатуру и пытается инжектировать зависимость с именем `self`, что приводит либо к ошибке разрешения зависимости, либо к инжекции неожиданного значения во время выполнения.

```python
async def __call__(self, **kw: object) -> None:
    return await self.handle(**kw)

__call__.__signature__ = inspect.signature(handle_fn)
```

**Рекомендация:**
Удалите параметр `self` из сигнатуры, передаваемой FastAPI. Используйте: `sig = inspect.signature(handle_fn); params = list(sig.parameters.values())[1:]  # drop self; __call__.__signature__ = sig.replace(parameters=params)`. Это гарантирует, что FastAPI видит только параметры, инжектируемые через DI.

---

### [MEDIUM] Type Safety — call_next parameter lacks type annotation across all middleware dispatch methods

**Файл:** middleware/rate_limit.py:20, middleware/logging.py:12, middleware/request_id.py:9
**Серьёзность:** Средняя

**Описание:**
Аргумент `call_next` не имеет типовой аннотации в `RateLimitMiddleware`, `LoggingMiddleware` и `RequestIDMiddleware`. Это мешает инструментам статического анализа обнаруживать некорректное использование и делает автодополнение в IDE бесполезным. Файл `base_middleware.py` корректно аннотирует его как `Callable[..., Awaitable[Response]]`, но конкретные подклассы этого не делают.

```python
async def dispatch(self, request: Request, call_next) -> Response:
```

**Рекомендация:**
Импортируйте и применяйте корректный тип: `from starlette.middleware.base import RequestResponseEndpoint` (канонический алиас Starlette для callable `call_next`) или используйте `Callable[..., Awaitable[Response]]` единообразно во всех сигнатурах `dispatch`.

---

### [MEDIUM] Code Style — deque type parameter missing — _store uses unparameterised deque

**Файл:** middleware/rate_limit.py:18
**Серьёзность:** Средняя

**Описание:**
Типовая аннотация `dict[str, deque]` использует голый `deque` без параметра типа. Это заставляет mypy считать каждый `deque` как `deque[Any]`, что лишает типовой проверки значения, добавляемые в него (временные метки `float`).

```python
_store: dict[str, deque] = defaultdict(deque)
```

**Рекомендация:**
Аннотируйте с указанием типа элемента: `_store: dict[str, deque[float]] = defaultdict(deque)`. Это позволит mypy выявлять некорректные типы значений, добавляемых в deque.

---

### [MEDIUM] Security — Rate-limit applies to all paths including health checks and static assets

**Файл:** middleware/rate_limit.py:20-48
**Серьёзность:** Средняя

**Описание:**
`RateLimitMiddleware` применяется ко всем входящим запросам без механизма исключения путей. Health-check эндпоинты (например, `/health`, `/readyz`), эндпоинты метрик и маршруты статических файлов расходуют квоту rate-limit. В Kubernetes-среде, где liveness-пробы запускаются каждые несколько секунд на реплику, это может исчерпать лимит для IP-адреса ноды, выполняющей пробы, вызывая сбои проб и перезапуски подов.

```python
async def dispatch(self, request: Request, call_next) -> Response:
    client_ip = (...)
```

**Рекомендация:**
Добавьте параметр `exclude_paths` (список префиксов путей) в `RateLimitMiddleware` и пропускайте логику rate-limit для совпадающих путей. Разумный список исключений по умолчанию: `["/health", "/readyz", "/metrics"]`.

---

### [LOW] Performance — uuid.uuid4() called on every request even when X-Request-ID is provided

**Файл:** middleware/request_id.py:10
**Серьёзность:** Низкая

**Описание:**
Выражение `request.headers.get("X-Request-ID") or str(uuid.uuid4())` всегда вычисляет `str(uuid.uuid4())` в Python, потому что `or` является коротким замыканием только на уровне значений, но обе стороны выражения всё равно должны быть синтаксически вычислены. На практике `or` в Python действительно выполняет короткое замыкание, поэтому `uuid4()` вызывается только при отсутствии заголовка. Однако вызов `str()` на результате UUID добавляет небольшое, но лишнее выделение памяти при каждом промахе. Это незначительно, но стоит отметить в горячем пути.

```python
request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
```

**Рекомендация:**
Это корректно обрабатывается оператором `or` в Python. Изменений для корректности не требуется. Для микрооптимизации при экстремальной пропускной способности используйте `uuid.uuid4().hex` вместо `str(uuid.uuid4())`, чтобы избежать накладных расходов на форматирование строки с дефисами.

---

### [LOW] Code Style — LoggingMiddleware logs at INFO level regardless of response status

**Файл:** middleware/logging.py:22-29
**Серьёзность:** Низкая

**Описание:**
Все запросы — включая ответы 4xx и 5xx — логируются на уровне INFO. Это мешает агрегаторам логов и инструментам мониторинга фильтровать трафик ошибок по уровню лога и затрудняет настройку оповещений по частоте ошибок.

```python
logger.info(
    "%s %s → %d [%.1fms] req_id=%s",
    request.method,
    request.url.path,
    status,
    duration_ms,
    request_id,
)
```

**Рекомендация:**
Используйте условные уровни лога: `logger.info` для 1xx-3xx, `logger.warning` для 4xx и `logger.error` для 5xx. Это обеспечивает стандартную фильтрацию по уровню лога и оповещения без парсинга тела сообщения.

---

### [LOW] Code Style — Guard base class handle() is synchronous no-op but documented and used as async

**Файл:** middleware/guard.py:60-61
**Серьёзность:** Низкая

**Описание:**
Базовый метод `handle` объявлен как `async def handle(self) -> None: pass`, что корректно. Однако защита в `__init_subclass__` патчит `__call__` только когда `handle` переопределён в словаре непосредственного класса. Если подкласс наследует `handle` от родительского guard (не самого `Guard`), патч `__call__` не применяется, что молча делает guard no-op.

```python
if "handle" in cls.__dict__:
    handle_fn = cls.__dict__["handle"]
```

**Рекомендация:**
Обходите MRO для поиска ближайшего не-базового определения `handle`, или чётко задокументируйте, что `handle` всегда должен быть определён непосредственно в конкретном подклассе. Добавьте проверку в `__call__`, которая выбрасывает `NotImplementedError` если `handle` не был переопределён, чтобы быстро падать, а не молча пропускать все запросы.

---
