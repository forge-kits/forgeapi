# Аудит: Telescope & CLI модули

## Краткое резюме

Аудит 9 файлов модуля telescope и 4 файлов CLI выявил 14 находок: 2 высокой, 7 средней и 5 низкой/информационной степени серьёзности. Наиболее критичные проблемы: (1) весь тело запроса (включая пароли в login-payload) и тело JSON-ответа сохраняются в памяти дословно и транслируются через WebSocket — очистка чувствительных полей не выполняется; (2) `_caller_location()` вызывает `traceback.extract_stack()` при каждом SQL-execute, добавляя O(глубина_стека) накладных расходов к каждому запросу; (3) словарь `_index` класса `DebugStore` ничем не ограничен, и записи, вытесненные из deque, остаются как устаревшие ссылки до следующего вызова `push()`; (4) окружение Jinja2 создаётся без автоэкранирования, а предоставляемые пользователем имена (`class_name`, `table_name`, `tag`) передаются в шаблоны напрямую; (5) параметр `name` в `generate_cmd` не проходит валидацию перед интерполяцией в пути файлов и контекст шаблонов; (6) обёртки `tortoise_hook` не оборачивают оригинальный вызов в `try/except`, поэтому исключение при записи приводит к потере результата запроса. CLI `db_cmd` безопасно использует `subprocess.run` со списком аргументов (без `shell=True`), что исключает инъекцию через оболочку.

## Находки

### [HIGH] Sensitive Data Exposure — Тела запросов и ответов сохраняются и транслируются без очистки на уровне полей

**Файл:** telescope/middleware.py:78,104
**Серьёзность:** Высокая

**Описание:**
Middleware сохраняет полностью разобранный payload запроса (строка 78) и полное тело ответа (строка 104) в `RequestEntry`, после чего `DebugStore.push()` немедленно транслирует `entry.to_dict()` через WebSocket всем подключённым браузерам (store.py:155-157). Никакой очистки чувствительных полей, таких как `password`, `secret`, `token`, `credit_card` и т.д., не производится. Тело POST /auth/login вида `{"email":"x","password":"hunter2"}` сохраняется дословно в памяти для до 200 запросов и отправляется в реальном времени любому WebSocket-слушателю. Заголовки запроса `Authorization` и `Cookie` маскируются (что хорошо), однако поля тела — нет.

```python
entry = DebugStore.new_entry(
    ...,
    payload=_parse_payload(body_bytes, content_type),  # полное тело
)
...
entry.response_body = _parse_payload(b"".join(resp_chunks), resp_content_type)  # полный ответ
```

**Рекомендация:**
Определите настраиваемый набор чувствительных имён полей (например, `SENSITIVE_BODY_FIELDS = frozenset({'password','secret','token','access_token','refresh_token','credit_card'})`). В `_parse_payload` (или в отдельном вспомогательном методе `_scrub_payload`) рекурсивно обходите разобранные JSON-словари и заменяйте значения, чьи ключи входят в этот набор, на `'***'`. Применяйте ту же очистку к телам ответов.

---

### [HIGH] Performance Impact — traceback.extract_stack() вызывается при каждом SQL-execute и добавляет значительные накладные расходы

**Файл:** telescope/hooks/tortoise_hook.py:23-28
**Серьёзность:** Высокая

**Описание:**
`_caller_location()` вызывает `traceback.extract_stack()` внутри каждой обёртки SQL-execute (`execute_query`, `execute_insert`, `execute_many`, `execute_script`). `extract_stack()` обходит весь стек вызовов Python и создаёт объекты фреймов для каждого фрейма. На нетривиальном стеке это 30-80 фреймов, каждый из которых требует форматирования строк. При запросе, выполняющем 20 SQL-запросов (типично при N+1), это добавляет 20 полных обходов стека, каждый занимающий 0.1-0.5 мс, что даёт 2-10 мс накладных расходов, невидимых для приложения. Также отсутствует ограничение на количество объектов `SqlRecord`, добавляемых в `entry.queries`, поэтому N+1 цикл из 1000 итераций разрастёт список до 1000 записей.

```python
def _caller_location() -> str:
    for frame in reversed(traceback.extract_stack()):
        path = frame.filename.replace("\\", "/")
        if not any(skip in path for skip in _SKIP_IN_PATH):
            return f"{frame.filename}:{frame.lineno} in {frame.name}"
    return "unknown"
```

**Рекомендация:**
1. Кешируйте обход стека, используя `sys._getframe()` для ручного обхода фреймов в цикле Python — это позволяет избежать создания объектов `FrameSummary` для ненужных фреймов. 2. Добавьте ограничение на количество записей на запрос (например, `MAX_QUERIES_PER_REQUEST = 500`) и прекращайте добавление по достижении предела, добавив одну сигнальную запись с пометкой об усечении. 3. Рассмотрите возможность сделать сбор информации о расположении вызывающего кода опциональным через флаг конфигурации, по умолчанию отключённым в близких к production средах.

---

### [MEDIUM] Memory Leak — DebugStore._index может содержать устаревшие ссылки после гонки при вытеснении из deque

**Файл:** telescope/store.py:148-153
**Серьёзность:** Средняя

**Описание:**
`DebugStore.push()` проверяет `len(cls._store) == cls._store.maxlen` перед добавлением, читает самую старую запись из `cls._store[-1]`, затем вызывает `appendleft()`. Поскольку `deque.appendleft` на полном deque с `maxlen` атомарно отбрасывает крайний правый элемент, последовательность «проверить-удалить» корректна только в однопоточном event loop. Однако, если два корутина вызывают `push()` одновременно, проверка длины и операция с deque не являются атомарными, и id вытесненной записи может не совпасть с `oldest.id`. На практике: если `DebugStore.clear()` вызывается между проверкой длины и pop (например, из обработчика WebSocket clear), `oldest` будет ссылаться на уже удалённую из `_index` запись, и `_index.pop()` окажется no-op, оставляя индекс в несогласованном состоянии. `_index` — это обычный словарь без `maxlen`, который при некорректной очистке становится неограниченным хранилищем ссылок.

```python
if len(cls._store) == cls._store.maxlen:
    oldest = cls._store[-1]       # может быть уже вытеснен конкурентным clear()
    cls._index.pop(oldest.id, None)
cls._store.appendleft(entry)
cls._index[entry.id] = entry
```

**Рекомендация:**
Замените ручную предварительную очистку вытеснения постфактум-согласованием: после `appendleft` пересоберите `_index` из текущего содержимого deque (O(maxlen), но ограниченно). Либо унаследуйте от deque подкласс, вызывающий callback при вытеснении, или используйте ограниченный `OrderedDict`. Для защиты от конкурентного `clear()` используйте `threading.Lock` или `asyncio.Lock` вокруг критической секции push/clear.

---

### [MEDIUM] Exception Handling — Обёртки tortoise hook не записывают запросы при исключении в underlying execute

**Файл:** telescope/hooks/tortoise_hook.py:43-50
**Серьёзность:** Средняя

**Описание:**
Все четыре фабрики обёрток (`_make_query_wrapper`, `_make_insert_wrapper`, `_make_many_wrapper`, `_make_script_wrapper`) вызывают `_record()` только на пути успешного выполнения после `result = await orig(...)`. Если `orig` генерирует исключение, хронометраж отбрасывается и никакой `SqlRecord` не добавляется. Это означает, что упавшие запросы (ошибки соединения, нарушения ограничений, синтаксические ошибки) невидимы в UI Telescope, что затрудняет диагностику ошибочных сценариев. Кроме того, поскольку `_record()` вызывается после `await`, если `orig` генерирует исключение, оно распространяется без записи запроса.

```python
t = time.perf_counter()
result = await orig(self, query, values)   # если возникает исключение, _record никогда не вызывается
_record(query, values, round((time.perf_counter() - t) * 1000, 3), loc)
return result
```

**Рекомендация:**
Оберните оригинальный вызов в `try/except` и записывайте в блоке `finally`:

```python
try:
    result = await orig(self, query, values)
except Exception as exc:
    _record(query, values, round((time.perf_counter() - t) * 1000, 3), loc, error=str(exc))
    raise
else:
    _record(query, values, round((time.perf_counter() - t) * 1000, 3), loc)
return result
```

Добавьте опциональное поле `error` в `SqlRecord`.

---

### [MEDIUM] Exception Handling — Патченый dispatch в events_hook поглощает ошибки записи и теряет контекст события

**Файл:** telescope/hooks/events_hook.py:21-30
**Серьёзность:** Средняя

**Описание:**
Функция `_patched_dispatch` вызывает `self.listeners_for(type(event))` перед ожиданием `_orig_dispatch`. Если `listeners_for` генерирует исключение (например, тип события не зарегистрирован или внутреннее состояние `EventBus` повреждено), исключение распространяется из `_patched_dispatch` и оригинальный dispatch никогда не вызывается, ломая приложение. Блок записи не обёрнут в `try/except`. С другой стороны, если `_orig_dispatch` генерирует исключение, `EventRecord` уже добавлен (с информацией о слушателях), но поле ошибки не захватывается.

```python
async def _patched_dispatch(self: EventBus, event: object) -> None:
    entry = get_current()
    if entry is not None:
        listeners = self.listeners_for(type(event))   # может генерировать исключение
        entry.events.append(EventRecord(...))
    await _orig_dispatch(self, event)                 # исключение не захватывается
```

**Рекомендация:**
Оберните весь блок записи в `try/except Exception` и логируйте любые ошибки записи без повторной генерации, чтобы баг инструментирования Telescope никогда не ломал диспетчеризацию событий:

```python
try:
    listeners = self.listeners_for(type(event))
    entry.events.append(EventRecord(...))
except Exception:
    logger.debug('Telescope: event recording failed', exc_info=True)
await _orig_dispatch(self, event)
```

---

### [MEDIUM] Exception Handling — emit() в logging_hook не защищён от рекурсии для дочерних логгеров

**Файл:** telescope/hooks/logging_hook.py:17-27
**Серьёзность:** Средняя

**Описание:**
`DebugLogHandler.emit()` пропускает только точные имена логгеров `'forgeapi.telescope'` и `'forgeapi.access'`. Иерархия логирования Python означает, что любой логгер с именем вроде `'forgeapi.telescope.foo'` или `'forgeapi.telescope.store'` будет распространяться до корневого логгера и достигнет `DebugLogHandler`, поскольку проверка `name in _SKIP_LOGGERS` проверяет точное совпадение, а не префикс. Если любой дочерний элемент `forgeapi.telescope` генерирует запись лога, что в свою очередь вызывает дополнительное логирование, это может привести к неограниченной рекурсии. Также `emit()` вызывает `self.format(record)` и `self.formatTime(record)`, которые могут генерировать исключения при некорректных строках форматирования `%` в сообщении записи.

```python
_SKIP_LOGGERS = frozenset({"forgeapi.telescope", "forgeapi.access"})

def emit(self, record: logging.LogRecord) -> None:
    if record.name in self._SKIP_LOGGERS:  # только точное совпадение, не префикс
        return
```

**Рекомендация:**
Измените проверку пропуска на совпадение по префиксу: `if record.name == name or record.name.startswith(name + ".") for name in _SKIP_LOGGERS`. Оберните `self.format(record)` в `try/except` и вызывайте `self.handleError(record)` при ошибке (стандартный контракт `logging.Handler`). Рассмотрите также пропуск записей от логгера `'asyncio'` для снижения шума.

---

### [MEDIUM] Security — Окружение Jinja2 создаётся без автоэкранирования — имена, контролируемые пользователем, передаются в шаблоны

**Файл:** cli/commands/generate_cmd.py:96-99
**Серьёзность:** Средняя

**Описание:**
Функция `_render()` создаёт окружение Jinja2 с отключённым автоэкранированием (по умолчанию). Значения `class_name`, `table_name`, `url_prefix`, `tag` и `models_module`, производные от аргументов CLI, предоставленных пользователем (позиционный аргумент `name`), передаются напрямую в контекст шаблона. Хотя это инструмент генерации кода (не веб-приложение), специально сформированное имя вроде `'User\n\nimport os; os.system("rm -rf /")\n#'` может инъецировать произвольный Python-код в генерируемые `.py` файлы. Это риск цепочки поставок / рабочей станции разработчика при коммите и выполнении сгенерированных файлов.

```python
def _render(template_name: str, **context) -> str:
    from jinja2 import Environment, FileSystemLoader
    templates_dir = Path(__file__).parent.parent / "templates"
    env = Environment(loader=FileSystemLoader(str(templates_dir)), keep_trailing_newline=True)
    return env.get_template(template_name).render(**context)
```

**Рекомендация:**
Валидируйте аргумент `name` до передачи в `_render()`: требуйте соответствия строгому паттерну, например `r'^[A-Za-z][A-Za-z0-9]*$'` (чистый CamelCase, без подчёркиваний, без спецсимволов), и отклоняйте несоответствующие входные данные с понятным сообщением об ошибке. Это корректная защита, а не автоэкранирование (которое предназначено для HTML, не для Python-кода). Добавьте валидацию в `run_make()` сразу после вычисления `class_name`.

---

### [MEDIUM] Unsafe File Operations — Предоставленный пользователем аргумент 'name' используется для построения путей файловой системы без санитизации

**Файл:** cli/commands/generate_cmd.py:126,241
**Серьёзность:** Средняя

**Описание:**
`module_name`, вычисленный из предоставленного пользователем аргумента `name` (через `_to_snake`), используется напрямую как имя файла (например, `Path(st.models_dir) / f'{file_name}.py'`). `_to_snake` только переводит в нижний регистр и вставляет подчёркивания между словами CamelCase — он не удаляет символы обхода пути. Входные данные вроде `'../../../etc/cron.d/evil'` пройдут `_to_snake` без изменений (нет заглавных букв), и результирующий путь запишет файл за пределами директории проекта. Аналогично, параметр `alias` в `_gen_model` используется для имени файла без какой-либо валидации пути.

```python
file_name = _to_snake(alias[0].upper() + alias[1:]) if alias else module_name
file_path = Path(st.models_dir) / f"{file_name}.py"
```

**Рекомендация:**
После вычисления `module_name` и `file_name` убедитесь, что результирующий `Path` не выходит за пределы предполагаемой директории: `resolved = (base_dir / file_name).resolve(); assert resolved.parent == base_dir.resolve()`. Либо валидируйте `name` и `alias` с тем же строгим regex `r'^[A-Za-z][A-Za-z0-9]*$'` до любого построения пути.

---

### [MEDIUM] N+1 Query Risk — tortoise_hook обнаруживает отдельные запросы, но не предоставляет алертинга или группировки N+1

**Файл:** telescope/hooks/tortoise_hook.py:31-39
**Серьёзность:** Средняя

**Описание:**
Хук корректно записывает каждый отдельный вызов SQL-execute, но никакого анализа для обнаружения N+1 паттернов (один и тот же шаблон запроса, выполняемый N раз в запросе) не производится. UI Telescope покажет 51 отдельный SELECT-запрос при загрузке 50 связанных объектов конечной точкой списка без `prefetch_related`, но никакого предупреждения или агрегации не будет. Пользователи должны вручную считать дублирующиеся паттерны запросов. Это пробел на уровне дизайна, а не баг, однако он значительно снижает диагностическую ценность telescope для проблемы N+1, которую он призван выявлять.

```python
def _record(sql: str, params: Any, duration_ms: float, location: str) -> None:
    entry = get_current()
    if entry is not None:
        entry.queries.append(SqlRecord(
            sql=sql,
            params=params,
            duration_ms=duration_ms,
            location=location,
        ))
```

**Рекомендация:**
В `RequestEntry.summary()` (или на шаге постфактум-анализа) группируйте запросы по их нормализованному шаблону SQL (убирайте литеральные значения с помощью простого regex или сравнивая запросы, отличающиеся только параметрами в WHERE-выражении). Когда один и тот же шаблон появляется более настраиваемого порога раз (по умолчанию: 3), добавляйте поле `n_plus_one_warning` в сводный словарь. Это можно сделать дёшево на этапе `summary()` без изменения пути записи.

---

### [LOW] Performance Impact — Тело ответа полностью буферизуется в памяти перед отправкой клиенту

**Файл:** telescope/middleware.py:85-94
**Серьёзность:** Низкая

**Описание:**
`capture_send` накапливает все чанки `http.response.body` в `resp_chunks` (список байтов). Тело объединяется только после завершения приложения (строка 104). Для потоковых ответов или больших JSON-payload (например, конечная точка отчёта, возвращающая 10 МБ данных) это означает, что всё тело хранится в RAM как отдельные объекты байтов до их объединения. В сочетании с хранилищем на 200 записей, в худшем случае это 200 * 10 МБ = 2 ГБ буферизованных данных ответа. Функция `_parse_payload` применяет усечение до 2000 символов только для не-JSON типов содержимого; для `application/json` она разбирает всё тело целиком.

```python
resp_chunks: list[bytes] = []
...
elif message["type"] == "http.response.body":
    resp_chunks.append(message.get("body", b""))
...
entry.response_body = _parse_payload(b"".join(resp_chunks), resp_content_type)
```

**Рекомендация:**
Ограничьте общее количество байтов, буферизуемых на ответ: прекращайте добавление в `resp_chunks` при достижении порога (например, 64 КБ) и устанавливайте флаг. В `_parse_payload` также применяйте усечение к JSON-содержимому: после `json.loads` сериализуйте обратно в строку и усекайте при `len > MAX_BODY_CHARS`, или усекайте сырые байты до разбора. Предоставьте `MAX_RESPONSE_BODY_BYTES` как настраиваемую переменную.

---

### [LOW] Memory Leak — Список ConnectionManager._connections не ограничен, и мёртвые соединения накапливаются до следующего broadcast

**Файл:** telescope/store.py:92-116
**Серьёзность:** Низкая

**Описание:**
`ConnectionManager` накапливает объекты WebSocket в `self._connections` без ограничений. Мёртвые соединения удаляются только во время `broadcast()`, когда вызов `send_json` генерирует исключение. Если новые запросы не поступают (broadcast не запускается), мёртвые соединения остаются в списке бесконечно. В сценарии, когда множество недолговечных клиентов подключаются (например, вкладка браузера многократно открывает и закрывает панель devtools), список растёт монотонно до следующего broadcast. Метод `connect()` также не проверяет на дублирование регистраций.

```python
async def connect(self, ws: Any) -> None:
    await ws.accept()
    self._connections.append(ws)  # без ограничений, без проверки на дубликаты
```

**Рекомендация:**
Добавьте ограничение максимального числа соединений (например, 10 одновременных клиентов Telescope) и отклоняйте лишние соединения с фреймом закрытия. Либо периодически пингуйте все соединения и удаляйте не отвечающие. Для устранения дублирования проверяйте, находится ли `ws` уже в `self._connections`, перед добавлением.

---

### [LOW] Exception Handling — generate_schema_cmd молча поглощает ошибки импорта модели, скрывая реальные сбои

**Файл:** cli/commands/generate_schema_cmd.py:303-306
**Серьёзность:** Низкая

**Описание:**
Голый `except Exception` в `run()` перехватывает все ошибки из `_load_model_fields` (который вызывает `importlib.import_module`) и только выводит `'note: model not found'`. Это маскирует реальные ошибки импорта, такие как `SyntaxError` в файле модели, `ImportError` отсутствующей зависимости или ошибки конфигурации базы данных. Пользователь не получает трейсбек, и команда продолжает работу, генерируя заглушки схем, которые могут быть некорректными.

```python
try:
    fields, extra_imports = _load_model_fields(class_name, module_dotted)
except Exception:
    typer.echo(f"  note: model '{class_name}' not found — generating stubs")
```

**Рекомендация:**
Различайте `ModuleNotFoundError` / `AttributeError` (файл модели действительно отсутствует) и другие исключения. Повторно генерируйте или выводите предупреждение с `exc_info` для неожиданных ошибок:

```python
except ModuleNotFoundError:
    typer.echo(f"  note: model '{class_name}' not found — generating stubs")
except Exception as exc:
    typer.echo(f"  warning: could not load model '{class_name}': {exc}", err=True)
```

---

### [LOW] Exception Handling — db_cmd.run() не обрабатывает OSError или FileNotFoundError из subprocess.run()

**Файл:** cli/commands/db_cmd.py:45
**Серьёзность:** Низкая

**Описание:**
`subprocess.run(cmd, env=env)` вызывается без `try/except`. Если бинарный файл tortoise существует на диске, но не является исполняемым, или если ОС отклоняет вызов exec по любой причине (отказ в доступе, повреждённый бинарный файл), генерируется `OSError` или `PermissionError` и распространяется как необработанное исключение с трейсбеком Python вместо понятного сообщения об ошибке для пользователя. `_find_tortoise_bin()` проверяет только существование пути (`path.exists()`), но не то, является ли он исполняемым.

```python
result = subprocess.run(cmd, env=env)
sys.exit(result.returncode)
```

**Рекомендация:**
Оберните `subprocess.run` в `try/except OSError` и выведите понятную ошибку:

```python
try:
    result = subprocess.run(cmd, env=env)
except OSError as exc:
    typer.echo(f"Error: failed to execute tortoise binary: {exc}", err=True)
    raise typer.Exit(code=1)
```

Также добавьте проверку `os.access(tortoise_bin, os.X_OK)` в `_find_tortoise_bin` перед возвратом пути.

---

### [INFO] Security — WebSocket-эндпоинт Telescope не имеет аутентификации — данные всех запросов доступны любому локальному клиенту

**Файл:** telescope/router.py:10-25
**Серьёзность:** Информационная

**Описание:**
WebSocket-эндпоинт `/_forge/telescope/ws` подключён без какой-либо проверки аутентификации. Любой процесс или вкладка браузера, способная достичь URL сервера (включая другие вкладки браузера, расширения браузера или клиентов локальной сети при привязке сервера к `0.0.0.0`), может подключиться и получать живой поток всех записей запросов, включая сохранённые payload и тела ответов. Эндпоинт также принимает команду `clear` от любого подключённого клиента, позволяя неаутентифицированным пользователям очищать хранилище. Это намеренно является функцией только для разработки, однако нет никакого принуждения к тому, чтобы она была включена только в среде разработки.

```python
@router.websocket("/ws")
async def telescope_ws(ws: WebSocket) -> None:
    await manager.connect(ws)  # без проверки аутентификации
    await ws.send_json({"type": "init", "data": [e.to_dict() for e in DebugStore.all()]})
```

**Рекомендация:**
Добавьте опциональную проверку секретного токена (например, сравнивайте параметр запроса `?token=` с настроенной переменной окружения `TELESCOPE_SECRET`) до вызова `manager.connect()`. Если токен отсутствует или неверен, закрывайте WebSocket с кодом `4401`. Чётко задокументируйте, что Telescope никогда не должен быть включён (`debug=True`) в production-развёртываниях.

---
