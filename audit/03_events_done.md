# Аудит: Events модуль

## Краткое резюме

Модуль событий ForgeAPI содержит 15 находок в 4 файлах. Наиболее критичные проблемы: (1) синглтон `get_instance()` имеет состояние гонки при конкурентном асинхронном доступе без какой-либо блокировки; (2) подклассы `BaseException` (включая `KeyboardInterrupt` и `SystemExit`) молча перехватываются и сбрасываются в `_run_all`, потому что `isinstance(result, Exception)` не покрывает их при использовании `asyncio.gather` с `return_exceptions=True`; (3) `EventBus.reset()` вызывает `task.cancel()`, но никогда не ожидает его завершения, оставляя корутину запущенной; (4) операции с Redis в `_dedup_check` и `dispatch` не имеют обработки ошибок, поэтому любой сбой Redis молча прерывает обработку события; (5) `from_dict` выбрасывает голый `KeyError` для неизвестных типов событий, который всплывает как необработанное исключение в цикле подписчика; (6) `_serialize` в `redis_bus.py` импортирует Tortoise внутри горячего пути сериализации при каждом вызове; (7) `connect()` молча заменяет уже открытое соединение при повторном вызове, утекая старое соединение. Дополнительные находки среднего уровня серьёзности включают: не потокобезопасный синглтон, неограниченный рост списка слушателей без защиты от дублирования, и `hashlib.md5` без `usedforsecurity=False`, что вызывает `ValueError` на системах с FIPS.

## Находки

### [CRITICAL] [Exception Handling] — Подклассы BaseException молча сбрасываются в цикле gather в _run_all

**Файл:** events/bus.py:315
**Серьёзность:** Критическая

**Описание:**
`asyncio.gather` с `return_exceptions=True` возвращает как подклассы `Exception`, так и подклассы `BaseException` (`KeyboardInterrupt`, `SystemExit`, `asyncio.CancelledError`) в виде результатов. Проверка `isinstance(result, Exception)` перехватывает только подклассы `Exception`, поэтому подклассы `BaseException` молча отбрасываются — без логирования и без повторного выброса. Это означает, что `CancelledError`, распространённый из слушателя, потребляется бесследно, а `SystemExit` внутри слушателя теряется полностью.

```python
for listener, result in zip(listeners, results):
    if isinstance(result, Exception):
        logger.error(...)
```

**Рекомендация:**
Изменить проверку на `isinstance(result, BaseException)` и отдельно повторно выбрасывать экземпляры `CancelledError` или обрабатывать их явно:
```python
for listener, result in zip(listeners, results):
    if isinstance(result, asyncio.CancelledError):
        raise result  # propagate cancellation
    if isinstance(result, BaseException):
        logger.error(...)
```

---

### [CRITICAL] [Race Condition] — Не потокобезопасный синглтон get_instance без блокировки

**Файл:** events/bus.py:78
**Серьёзность:** Критическая

**Описание:**
`get_instance()` проверяет и устанавливает `_instance` в двух отдельных шагах без блокировки. В окружениях, использующих потоки вместе с asyncio (например, Uvicorn с несколькими воркерами в одном процессе или тест-раннеры), два потока могут одновременно увидеть `_instance is None` и каждый создаст свой собственный `EventBus`, что приведёт к двум независимым реестрам. Слушатели, зарегистрированные в одном экземпляре, никогда не получат события, отправленные через другой.

```python
if cls._instance is None:
    cls._instance = cls()
return cls._instance
```

**Рекомендация:**
Защитить создание синглтона с помощью `threading.Lock`:
```python
_lock = threading.Lock()

@classmethod
def get_instance(cls) -> 'EventBus':
    if cls._instance is None:
        with _lock:
            if cls._instance is None:
                cls._instance = cls()
    return cls._instance
```

---

### [HIGH] [Async Issues] — reset() вызывает task.cancel() но никогда не ожидает задачу, оставляя корутину запущенной

**Файл:** events/bus.py:96
**Серьёзность:** Высокая

**Описание:**
`EventBus.reset()` вызывает `task.cancel()` на задаче подписчика, но является синхронным методом класса, поэтому никогда не ожидает отмены. Отменённая задача продолжает выполняться до тех пор, пока цикл событий не обработает `CancellationError`, что может произойти уже после того, как новый синглтон `EventBus` начнёт использоваться. В этот промежуток времени старый подписчик всё ещё может отправлять события в старый (уже отброшенный) реестр или записывать данные в закрытое Redis-соединение.

```python
if task and not task.done():
    task.cancel()
cls._instance = None
```

**Рекомендация:**
Сделать `reset()` асинхронным и ожидать отмену:
```python
@classmethod
async def reset(cls) -> None:
    if cls._instance is not None:
        task = getattr(cls._instance, '_subscriber_task', None)
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
    cls._instance = None
```
Для синхронных тестовых фикстур документировать, что teardown должен выполняться внутри цикла событий.

---

### [HIGH] [Redis Safety] — Отсутствие обработки ошибок при публикации в Redis в dispatch() — сбои Redis молча прерывают доставку событий

**Файл:** events/bus.py:293
**Серьёзность:** Высокая

**Описание:**
Когда `event.redis` равно `True`, `dispatch()` вызывает `await self._redis.publish(channel, payload)` без `try/except`. Любая ошибка Redis (обрыв соединения, таймаут, ошибка READONLY при переключении) распространяется как необработанное исключение в вызывающий код `dispatch()`. Событие теряется без отката к локальной доставке и без логирования на уровне шины. Та же проблема существует в `_dedup_check()` на строке 213.

```python
await self._redis.publish(channel, payload)
return
```

**Рекомендация:**
Обернуть операции Redis в `try/except` и определить стратегию отката:
```python
try:
    await self._redis.publish(channel, payload)
except Exception as exc:
    logger.error('Failed to publish event %s to Redis: %s', type(event).__name__, exc, exc_info=exc)
    # fallback: run locally
    await self._run_all(event, self.listeners_for(type(event)))
```
Применить тот же паттерн к `_dedup_check()`.

---

### [HIGH] [Exception Handling] — from_dict выбрасывает голый KeyError для неизвестного типа события — роняет цикл подписчика

**Файл:** events/event.py:97
**Серьёзность:** Высокая

**Описание:**
`Event.from_dict()` выполняет `klass = cls._registry[event_type]` без защиты от отсутствующих ключей. Если Redis-сообщение содержит тип события, класс которого никогда не был импортирован в этом процессе (например, кросс-сервисное событие или скользящее обновление с несовместимыми версиями), выбрасывается `KeyError`. Он перехватывается широким `except` в `_handle_redis_message` (bus.py:170), но логируется как ошибка десериализации. Более того, сообщение с отсутствующим полем `_event_type` вызывает `KeyError` на `data.pop('_event_type')`, который тоже молча проглатывается — что делает сообщение об ошибке вводящим в заблуждение.

```python
event_type = data.pop("_event_type")
klass = cls._registry[event_type]
```

**Рекомендация:**
Выбрасывать чёткое, описательное исключение:
```python
event_type = data.get('_event_type')
if not event_type:
    raise ValueError(f'Event dict missing _event_type key: {data!r}')
klass = cls._registry.get(event_type)
if klass is None:
    raise ValueError(f'Unknown event type {event_type!r}. '
                     f'Ensure the module defining it is imported.')
data.pop('_event_type')
```

---

### [HIGH] [Redis Safety] — connect() молча заменяет существующее соединение, утекая старый Redis-клиент

**Файл:** events/redis_bus.py:272
**Серьёзность:** Высокая

**Описание:**
`RedisBus.connect()` безусловно перезаписывает `self._redis`, не проверяя, существует ли уже соединение, и не закрывая его предварительно. Двойной вызов `connect()` (например, через `__aenter__`, вызванный дважды, или паттерн переподключения) утекает первый объект соединения — его нижележащий сокет никогда не закрывается, а любые активные pub/sub-подписки на нём остаются открытыми.

```python
self._redis = aioredis.from_url(self._url, decode_responses=True)
```

**Рекомендация:**
Защититься от двойного подключения:
```python
async def connect(self) -> None:
    if self._redis is not None:
        return  # already connected
    ...
    self._redis = aioredis.from_url(self._url, decode_responses=True)
```
Или вызывать `await self.disconnect()` первым, если переподключение намеренно.

---

### [HIGH] [Async Issues] — start_redis_subscriber() в EventBus не обрабатывает asyncio.CancelledError в блоке finally — возможна блокировка при завершении

**Файл:** events/bus.py:156
**Серьёзность:** Высокая

**Описание:**
Блок `finally` в `start_redis_subscriber()` вызывает `await pubsub.punsubscribe(...)` и `await pubsub.aclose()`. Если задача отменяется во время выполнения этих `await` (например, повторный сигнал отмены при завершении), `CancelledError` выбрасывается внутри блока `finally`, потенциально оставляя pubsub-соединение незакрытым. Для сравнения, `RedisBus.listen()` оборачивает блок `finally` в голый `except` — что является противоположной крайностью. Ни один из подходов не является корректным для продакшн-надёжности.

```python
finally:
    await pubsub.punsubscribe(f"{_CHANNEL_PREFIX}*")
    await pubsub.aclose()
    logger.debug("Redis subscriber stopped")
```

**Рекомендация:**
Использовать `asyncio.shield` или подавлять `CancelledError` при очистке:
```python
finally:
    with contextlib.suppress(Exception):
        await pubsub.punsubscribe(f'{_CHANNEL_PREFIX}*')
    with contextlib.suppress(Exception):
        await pubsub.aclose()
    logger.debug('Redis subscriber stopped')
```

---

### [MEDIUM] [Memory Leak] — Список слушателей не имеет дедупликации — двойная регистрация вызывает запуск обработчиков дважды на событие

**Файл:** events/bus.py:229
**Серьёзность:** Средняя

**Описание:**
`register()` безусловно добавляет в список слушателей. Если одна и та же функция зарегистрирована дважды для одного и того же класса события (например, `load_from_dir` вызывается дважды или модуль перезагружается), обработчик запускается дважды на каждый `dispatch`. Защита от дублирования отсутствует. Для идемпотентных обработчиков это проблема корректности; для неидемпотентных (отправка email, списание с карты) — критическая ошибка. Кэширование модулей в `_import_file` предотвращает двойную загрузку, но другие пути регистрации (`bus.on`, `listen`, `bus.register`) не защищены.

```python
def register(self, event_class: type, listener: Callable) -> None:
    self._listeners.setdefault(event_class, []).append(listener)
```

**Рекомендация:**
Проверять существующую регистрацию перед добавлением:
```python
def register(self, event_class: type, listener: Callable) -> None:
    bucket = self._listeners.setdefault(event_class, [])
    if listener not in bucket:
        bucket.append(listener)
    else:
        logger.warning('Listener %r already registered for %s, skipping duplicate', listener, event_class.__name__)
```

---

### [MEDIUM] [Memory Leak] — Множество _bg_tasks может расти без ограничений, если задачи создаются быстрее, чем завершаются

**Файл:** events/bus.py:70
**Серьёзность:** Средняя

**Описание:**
И `EventBus`, и `RedisBus` поддерживают множество `_bg_tasks: set[asyncio.Task]` и добавляют каждую fire-and-forget задачу в него (done_callback удаляет её по завершении). При высокой пропускной способности событий, если медленные слушатели или медленные вызовы Redis приводят к накоплению задач быстрее, чем они завершаются, множество растёт без ограничений и удерживает сильные ссылки на все ожидающие задачи и их замыкания (включая объект события и функцию-слушатель). Нет ограничения размера, нет таймаута и нет механизма drain при завершении.

```python
self._bg_tasks: set[asyncio.Task] = set()
...
self._bg_tasks.add(t)
t.add_done_callback(self._bg_tasks.discard)
```

**Рекомендация:**
Добавить настраиваемый лимит параллелизма и шаг drain при завершении:
```python
# On shutdown, await pending tasks:
async def drain(self, timeout: float = 30.0) -> None:
    if self._bg_tasks:
        await asyncio.wait(self._bg_tasks, timeout=timeout)
```
Рассмотреть использование семафора для ограничения параллельных фоновых задач.

---

### [MEDIUM] [Redis Safety] — Отсутствует логика переподключения в Redis-подписчике — один обрыв соединения навсегда убивает весь цикл обработки событий

**Файл:** events/bus.py:127
**Серьёзность:** Средняя

**Описание:**
И `start_redis_subscriber()`, и `RedisBus.listen()` подключаются один раз и бесконечно итерируют `pubsub.listen()`. Если Redis разрывает соединение (сетевой сбой, перезапуск Redis, таймаут keepalive), асинхронный генератор выбрасывает исключение, которое выходит из блока `try`, выполняет `finally` и корутина завершается. Задача-подписчик молча завершается. Никакие события больше не будут обрабатываться до перезапуска приложения. Нет цикла переподключения, нет оповещений, и завершение задачи неотличимо от штатного останова.

```python
try:
    async for message in pubsub.listen():
        if message["type"] != "pmessage":
            continue
        await self._handle_redis_message(message["data"])
finally:
    await pubsub.punsubscribe(...)
```

**Рекомендация:**
Обернуть цикл подключения в цикл повторных попыток с экспоненциальной задержкой:
```python
retry_delay = 1.0
while True:
    try:
        pubsub = self._redis.pubsub()
        await pubsub.psubscribe(...)
        async for message in pubsub.listen():
            ...
    except asyncio.CancelledError:
        break
    except Exception as exc:
        logger.error('Redis subscriber error, reconnecting in %.1fs: %s', retry_delay, exc)
        await asyncio.sleep(retry_delay)
        retry_delay = min(retry_delay * 2, 60.0)
```

---

### [MEDIUM] [Type Safety] — register() принимает любой Callable, но не проверяет, является ли он корутинной функцией

**Файл:** events/bus.py:220
**Серьёзность:** Средняя

**Описание:**
`register()` принимает `Callable` без проверки во время выполнения того, что callable является асинхронной функцией (т.е. `asyncio.iscoroutinefunction(listener)` равно `True`). Если передаётся обычная синхронная функция, вызов `listener(event)` внутри `_run_all` возвращает обычное значение, а не корутину. `asyncio.gather` тогда выбросит `TypeError: An asyncio.Future, a coroutine or an awaitable is required` — но эта ошибка всплывёт во время `dispatch`, а не при регистрации, что делает её очень трудно диагностируемой.

```python
def register(self, event_class: type, listener: Callable) -> None:
    self._listeners.setdefault(event_class, []).append(listener)
```

**Рекомендация:**
Добавить защиту на этапе регистрации:
```python
if not asyncio.iscoroutinefunction(listener):
    raise TypeError(
        f'Listener {listener!r} must be an async function (async def). '
        f'Synchronous callables are not supported.'
    )
```

---

### [MEDIUM] [Code Style / Performance] — _serialize() импортирует Tortoise ORM при каждом вызове внутри горячего пути

**Файл:** events/redis_bus.py:28
**Серьёзность:** Средняя

**Описание:**
`_serialize()` вызывается при каждом `emit()`. Внутри него, если объект имеет атрибут `_meta`, выполняется `from tortoise.models import Model as TortoiseModel` в теле функции. Python кэширует импорты модулей после первой загрузки, но поиск импорта (доступ к словарю `sys.modules` и разрешение атрибутов) всё равно происходит при каждом вызове, добавляя избыточные накладные расходы в сценариях с высокой пропускной способностью. Если Tortoise не установлен, `TortoiseModel` устанавливается в `None`, и защита `if TortoiseModel and isinstance(v, TortoiseModel)` молча пропускает фильтр, потенциально сериализуя несериализуемые объекты proxy-отношений.

```python
try:
    from tortoise.models import Model as TortoiseModel
except ImportError:
    TortoiseModel = None
```

**Рекомендация:**
Перенести импорт на уровень модуля с `try/except` при загрузке модуля:
```python
try:
    from tortoise.models import Model as _TortoiseModel
except ImportError:
    _TortoiseModel = None
```
Затем ссылаться на `_TortoiseModel` в `_serialize()` без повторного импорта.

---

### [MEDIUM] [Exception Handling] — listen() в RedisBus молча подавляет все исключения в блоке очистки finally

**Файл:** events/redis_bus.py:225
**Серьёзность:** Средняя

**Описание:**
Блок `finally` в `RedisBus.listen()` использует голый `except Exception: pass`, который подавляет каждое исключение при очистке — включая реальные ошибки, как например, нахождение pubsub-соединения в нерабочем состоянии, которые должны быть залогированы. Это делает post-mortem отладку проблем жизненного цикла соединения невозможной.

```python
finally:
    try:
        await pubsub.punsubscribe(pattern)
        await pubsub.aclose()
    except Exception:
        pass
```

**Рекомендация:**
Логировать подавленные ошибки очистки на уровне debug:
```python
finally:
    try:
        await pubsub.punsubscribe(pattern)
        await pubsub.aclose()
    except Exception as exc:
        logger.debug('RedisBus: error during pubsub cleanup: %s', exc)
    logger.debug('RedisBus: listener stopped')
```

---

### [LOW] [Code Style] — hashlib.md5 используется без usedforsecurity=False — вызывает ValueError на системах с FIPS

**Файл:** events/bus.py:353
**Серьёзность:** Низкая

**Описание:**
Python 3.9+ принимает ключевой аргумент `usedforsecurity` для функций hashlib. На системах, работающих в режиме FIPS (распространено в государственном и финансовом секторе США), вызов `hashlib.md5()` без `usedforsecurity=False` выбрасывает `ValueError: [digital envelope routines] unsupported`. MD5 здесь используется исключительно как стабильный хэш пути к файлу в строку (не в целях безопасности), поэтому флаг должен быть установлен в `False`.

```python
module_name = f"_fk_listener_{hashlib.md5(str(path.resolve()).encode()).hexdigest()}"
```

**Рекомендация:**
Передать `usedforsecurity=False`:
```python
module_name = f"_fk_listener_{hashlib.md5(str(path.resolve()).encode(), usedforsecurity=False).hexdigest()}"
```

---

### [LOW] [Type Safety] — Event._registry — это разделяемый словарь на уровне класса без защиты от коллизий имён

**Файл:** events/event.py:49
**Серьёзность:** Низкая

**Описание:**
`Event._registry` отображает имена классов (строки) на классы. Если два разных подкласса `Event` в разных модулях имеют одинаковое имя класса, второе определение молча перезаписывает первое в реестре. `from_dict()` тогда всегда будет восстанавливать второй класс, производя некорректные типы событий без какого-либо предупреждения. Это особенно опасно при автозагрузке файлов слушателей, где коллизии именования могут быть неочевидны.

```python
_registry: ClassVar[dict[str, type["Event"]]] = {}

def __init_subclass__(cls, **kwargs: Any) -> None:
    super().__init_subclass__(**kwargs)
    Event._registry[cls.__name__] = cls
```

**Рекомендация:**
Использовать полностью квалифицированное имя класса для избежания коллизий и предупреждать о перезаписи:
```python
def __init_subclass__(cls, **kwargs: Any) -> None:
    super().__init_subclass__(**kwargs)
    key = f'{cls.__module__}.{cls.__qualname__}'
    if key in Event._registry:
        logger.warning('Event class %r already registered, overwriting', key)
    Event._registry[key] = cls
```
Обновить `to_dict()` и `from_dict()` для использования того же полностью квалифицированного ключа.

---
