# Changelog

All notable changes to forge-kits are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/).
Note: during the solo-user phase breaking changes land directly (no
deprecation cycle) and are recorded under **Changed**/**Removed**.

## [Unreleased] — Laravel-style global refactor

### Added
- **Service Provider bootstrap.** `Core` is a thin orchestrator: each module
  ships a `Provider` (`forgeapi/<module>/provider.py`) with `register()`
  (module wiring, no user code) and `boot()` (user-code discovery) phases.
  Custom providers via the `providers` key in `config/project.py`.
  Base class: `forgeapi.foundation.Provider` (exported as `forgeapi.Provider`);
  helper `forgeapi.foundation.import_string`.
- **Python dict config** — `config/` directory is the only config format.
  Each `config/<section>.py` defines `config = {...}`; the filename is the
  section name. Custom sections allowed, reachable via
  `KitConfig.get("services.stripe.key")` dot access.
- `env()` helper (`from forgeapi import env`) — reads env vars, casts
  `"true"`/`"false"`/`"null"`.
- `config/database.py` needs only the `TORTOISE_ORM` dict — the loader
  derives the dotted path for the tortoise CLI
  (`config.database.TORTOISE_ORM`) from the file location. An explicit
  `config = {"tortoise_orm": "..."}` remains as an override for a
  non-standard location.
- New config sections: `http` (cors, rate_limit, request_id, access_log,
  middleware), `permissions` (`{"model": "database.models.user.User"}`),
  `project.debug`, `project.providers`.
- **Multi-guard auth from config**: `config/auth.py` defines named `guards`
  with per-guard `strategy`, `secret`, `model` (dotted path), etc.;
  `default` selects the facade default.
- `auth.extend(name, StrategyClass)` — custom auth strategies; every
  strategy implements `from_config(cfg: dict)`.
- Capability protocols `TokenIssuer`, `RefreshCapable`, `SessionIssuer`
  (`forgeapi.auth.contracts`) — `Guard`/facade dispatch on protocols;
  custom strategies get `token()` / `decode()` / cookie helpers for free.
- `Guard.authenticate(request, required=...)` public; `Guard.strategy` /
  `Guard.user_model` properties; `Guard.set_cookie()` / `Guard.delete_cookie()`.
- `auth_claims()` hook on user models to control token claims.
- New exceptions: `SessionExpiredError`, `SessionInvalidError`,
  `UserNotFoundError`; all auth errors carry a machine-readable `.code`
  exposed in the `WWW-Authenticate` challenge (`Bearer error="token_expired"`).

### Changed
- **`Core(app)` takes only the app.** Everything else is config-driven,
  convention over configuration: auth boots when `config/auth.py` exists;
  controllers/listeners/policies boot when their directories exist;
  Telescope via `"debug": True` in `config/project.py`; permissions boot
  automatically when a model in `models_dir` inherits `PermissionsMixin`
  (no config file — the mixin is the activation); pagination and cache
  always configured.
- Strategies raise domain exceptions (`TokenExpiredError`,
  `TokenInvalidError`, `SessionExpiredError`, `SessionInvalidError`)
  instead of `fastapi.HTTPException`. The single HTTP-translation point is
  `Guard.authenticate` — uniform 401 body and `WWW-Authenticate` header.
- `OptionalUser` / `optional_user()` semantics unified: absent credentials
  → `None`; present-but-invalid (incl. user gone from DB) → 401 always.
- `forgeapi init` scaffolds `config/*.py` and a one-line `Core(app)` main.
- **`TORTOISE_ORM` moved to `config/database.py`** (Laravel-style: connection
  params live in config/database). The scaffolded `app/config.py` is gone;
  the dotted path default is now `config.database.TORTOISE_ORM` (``config/``
  is a namespace package, importable by the tortoise CLI).
- Fixed lazy imports in `forgeapi.__getattr__` (auth exports crashed after
  the `AuthBackend` removal).
- `forgeapi init` no longer scaffolds any packaging files (`pyproject.toml`
  is gone, no `requirements.txt` either) — dependency management is the
  user's business. The `[tool.tortoise]` fallback is gone too —
  `forgeapi db:*` passes the config path explicitly. (The old pyproject
  template also declared a wrong `forgeapi[...]` PyPI name.)

### Removed
- **All `Core` feature kwargs** (`auth=`, `cors=`, `rate_limit=`,
  `pagination=`, `request_id=`, `events=`, `policies=`, `access_log=`,
  `controllers=`, `permissions=`, `middleware=`, `debug=`, `config_path=`) —
  moved to config sections.
- **`forgeapi.toml` support** — `load_config` raises with a migration hint;
  py-dict `config/` is the only format.
- Legacy flat auth config fields (`strategy`, `jwt_secret_env`,
  `access_ttl_minutes`, ...) and `AuthTomlConfig` — guards-only format.
- `forgeapi/auth/backend.py` tombstone.
- `Core._build_strategy` / `_build_jwt` / `_build_cookie` / `_build_telegram`
  — strategy construction lives in `Strategy.from_config` + the facade
  factory registry.

## [1.2.0] — 2026-06

Pre-changelog release. See git history.
