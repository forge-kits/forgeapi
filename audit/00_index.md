# ForgeAPI — Полный аудит кода

**Дата:** 2026-07-08
**Версия проекта:** 0.1.6
**Аудитор:** Claude Code (автоматический анализ)

## Статистика находок

| Серьёзность | Кол-во |
|-------------|--------|
| 🔴 Critical | 10 |
| 🟠 High     | 36 |
| 🟡 Medium   | 55 |
| 🟢 Low      | 26 |
| ℹ️ Info     | 1 |
| **Итого**   | **128** |

## Модули

| Файл | Модуль | Критических | High | Medium |
|------|--------|-------------|------|--------|
| [01_auth.md](01_auth_done.md) | Auth (JWT, Cookie, Telegram) | 2 | 5 | 9 |
| [02_permissions.md](02_permissions_done.md) | Permissions (RBAC) | 2 | 5 | 5 |
| [03_events.md](03_events.md) | Events (Bus, RedisBus) | 2 | 5 | 6 |
| [04_middleware.md](04_middleware.md) | Middleware | 2 | 6 | 6 |
| [05_core.md](05_core.md) | Core (exceptions, pagination, controllers) | 2 | 6 | 7 |
| [06_telescope_cli.md](06_telescope_cli.md) | Telescope & CLI | 0 | 2 | 7 |
| [07_tests.md](07_tests.md) | Test Suite | 0 | 7 | 15 |

## Топ-10 приоритетных задач

1. **[CRITICAL]** JWT algorithm not validated — algorithm confusion attack possible — `auth/strategies/jwt.py:128`
2. **[CRITICAL]** Mutable default argument on AuthUser.extra creates shared state across instances — `auth/models.py:8`
3. **[HIGH]** CookieStrategy: secure=False is the default — session cookies sent over plain HTTP in production — `auth/strategies/cookie.py:60`
4. **[HIGH]** Telegram HMAC comparison performed before auth_date expiry check — timing oracle on expired tokens — `auth/strategies/telegram.py:109-132`
5. **[HIGH]** JWT token type claim checked after decode but type field is user-controlled at issuance — `auth/strategies/jwt.py:165`
6. **[HIGH]** Cookie _verify swallows all exceptions during base64/JSON decode with no logging — `auth/strategies/cookie.py:183-186`
7. **[HIGH]** AuthUser.id typed as Any — downstream code receives untyped user identity — `auth/models.py:6`
8. **[CRITICAL]** assign_role and give_permission silently auto-create arbitrary roles and permissions — `permissions/mixins.py:175-196, permissions/models.py:44-56`
9. **[CRITICAL]** sync_permissions and sync_roles are non-atomic TOCTOU — concurrent requests can corrupt permission state — `permissions/mixins.py:131-136, permissions/mixins.py:207-212`
10. **[HIGH]** Every authenticated request issues 2-3 sequential DB round-trips with no in-process or distributed cache — `permissions/dependencies.py:27-43, permissions/mixins.py:41-63`

## Категории проблем

- **Security**: 23
- **Exception Handling**: 13
- **Code Style**: 10
- **Missing Edge Case**: 9
- **Type Safety**: 8
- **Correctness**: 8
- **Coverage Gap**: 8
- **Test Quality - Weak Assertion**: 6
- **Memory Leak**: 4
- **Performance**: 4
- **Race Condition**: 3
- **Redis Safety**: 3
- **Design**: 3
- **Async Issues**: 2
- **Performance Impact**: 2
- **Fixture Issue**: 2
- **Security - Privilege Escalation**: 1
- **Performance - No Caching**: 1
- **Performance - Duplicate DB Queries**: 1
- **Security - Logic Bug / Bypass**: 1
- **Security - Missing Guard Filtering**: 1
- **Security - Information Leakage**: 1
- **Security - Authorization Gap**: 1
- **Performance - Redundant Query**: 1
- **Security - Global Singleton Risk**: 1
- **Code Style - Naming Convention**: 1
- **Code Style - Missing Return Type Annotations**: 1
- **Code Style / Performance**: 1
- **Data Integrity**: 1
- **Thread Safety**: 1
- **Sensitive Data Exposure**: 1
- **Unsafe File Operations**: 1
- **N+1 Query Risk**: 1
- **Fixture Issue - Module-Level Shared State**: 1
- **Async Test Issue - Unawaited Background Task**: 1
- **Async Test Issue**: 1
