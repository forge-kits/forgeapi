# Changelog

Generated from git history by `scripts/gen_changelog.py` (Conventional Commits). Do not edit by hand.

## [1.7.1](https://github.com/forge-kits/forgeapi/releases/tag/v1.7.1) - 2026-10-13

### Features

- **cli:** Add make:job, make:policy, make:observer, make:provider ([`ebd1d5e`](https://github.com/forge-kits/forgeapi/commit/ebd1d5e))
- **queue:** Recover stuck jobs, queue:work/queue:run --queue ([`485025b`](https://github.com/forge-kits/forgeapi/commit/485025b))

### Fixes

- **scheduler:** Correct time storage on PostgreSQL with use_tz=False ([`c70acb6`](https://github.com/forge-kits/forgeapi/commit/c70acb6))

### Documentation

- Add MkDocs Material site and changelog generator for GitHub Pages ([`db0121e`](https://github.com/forge-kits/forgeapi/commit/db0121e))
- Document PostgreSQL fixes, stuck jobs, --queue and make:* commands ([`990ba49`](https://github.com/forge-kits/forgeapi/commit/990ba49))

## [1.7.0](https://github.com/forge-kits/forgeapi/releases/tag/v1.7.0) - 2026-10-13

### Features

- **config:** Project timezone, use_tz/timezone in generated database config ([`b7c5fc6`](https://github.com/forge-kits/forgeapi/commit/b7c5fc6))
- **cli:** Add forgeapi doctor, accept --help for every command ([`6f252a2`](https://github.com/forge-kits/forgeapi/commit/6f252a2))
- **queue:** Job.failed() hook and project timezone ([`c1c5a92`](https://github.com/forge-kits/forgeapi/commit/c1c5a92))
- **scheduler:** Cron, monthly/yearly, without_overlapping, timezone support ([`f4f827c`](https://github.com/forge-kits/forgeapi/commit/f4f827c))

### Fixes

- **database:** Stop infinite recursion in ForgeQuerySet.__getattr__ ([`e8a0f0e`](https://github.com/forge-kits/forgeapi/commit/e8a0f0e))

### Documentation

- Document new scheduler/queue/doctor features, trim Laravel mentions ([`469b263`](https://github.com/forge-kits/forgeapi/commit/469b263))

### Maintenance

- Drop pyjwt dependency and jwt strategy from tests ([`0a8de71`](https://github.com/forge-kits/forgeapi/commit/0a8de71))

## [1.6.8](https://github.com/forge-kits/forgeapi/releases/tag/v1.6.8) - 2026-09-29

### Features

- **storage:** Add ImageProcessor.ext() to set output format from a file extension ([`6fe92f7`](https://github.com/forge-kits/forgeapi/commit/6fe92f7))

## [1.6.5](https://github.com/forge-kits/forgeapi/releases/tag/v1.6.5) - 2026-09-17

### Features

- **controllers:** Support @route.websocket for websocket handlers ([`19c42cc`](https://github.com/forge-kits/forgeapi/commit/19c42cc))

## [1.6.4](https://github.com/forge-kits/forgeapi/releases/tag/v1.6.4) - 2026-09-15

### Features

- **controllers:** Add web flag to bypass base_prefix for Inertia/web routes ([`2de1357`](https://github.com/forge-kits/forgeapi/commit/2de1357))

### Tests

- Add auth, cli, core, permissions test suites ([`a763447`](https://github.com/forge-kits/forgeapi/commit/a763447))

### Maintenance

- Remove .idea from tracking, add to .gitignore ([`f11b639`](https://github.com/forge-kits/forgeapi/commit/f11b639))

## [1.6.3](https://github.com/forge-kits/forgeapi/releases/tag/v1.6.3) - 2026-09-14

_No notable changes._

## [1.6.2](https://github.com/forge-kits/forgeapi/releases/tag/v1.6.2) - 2026-09-10

_No notable changes._

## [1.6.1](https://github.com/forge-kits/forgeapi/releases/tag/v1.6.1) - 2026-09-08

### Fixes

- **scopes:** Use self.model instead of self._model in ForgeQuerySet.__getattr__ ([`5fb0a1d`](https://github.com/forge-kits/forgeapi/commit/5fb0a1d))

## [1.6.0](https://github.com/forge-kits/forgeapi/releases/tag/v1.6.0) - 2026-08-11

### Fixes

- Update test, update model config ([`9d368ac`](https://github.com/forge-kits/forgeapi/commit/9d368ac))

## [1.5.9](https://github.com/forge-kits/forgeapi/releases/tag/v1.5.9) - 2026-08-11

### Refactoring

- **broadcasting:** Driver-agnostic manager, keepalive ping, BroadcastConfig driver_options ([`cff741f`](https://github.com/forge-kits/forgeapi/commit/cff741f))

## [1.5.8](https://github.com/forge-kits/forgeapi/releases/tag/v1.5.8) - 2026-08-11

### Features

- **logging:** Add timestamp to debug log formatter ([`62bf4f9`](https://github.com/forge-kits/forgeapi/commit/62bf4f9))

## [1.5.7](https://github.com/forge-kits/forgeapi/releases/tag/v1.5.7) - 2026-08-11

### Fixes

- **permissions:** Auto-resolve guard from auth config, drop hardcoded "api" ([`32d8135`](https://github.com/forge-kits/forgeapi/commit/32d8135))

## [1.5.6](https://github.com/forge-kits/forgeapi/releases/tag/v1.5.6) - 2026-08-10

### Fixes

- **permissions:** Resolve default guard from auth._default, not hardcoded "api" ([`905b3df`](https://github.com/forge-kits/forgeapi/commit/905b3df))

## [1.5.5](https://github.com/forge-kits/forgeapi/releases/tag/v1.5.5) - 2026-08-10

### Fixes

- **permissions:** Scope guards to correct auth guard and namespace ([`c09fbe9`](https://github.com/forge-kits/forgeapi/commit/c09fbe9))

## [1.5.4](https://github.com/forge-kits/forgeapi/releases/tag/v1.5.4) - 2026-08-10

### Features

- **controllers:** Support Annotated guards in Controller.guards ([`13d5782`](https://github.com/forge-kits/forgeapi/commit/13d5782))

### Maintenance

- Add remaining test files to repo ([`fb31bd7`](https://github.com/forge-kits/forgeapi/commit/fb31bd7))

## [1.5.3](https://github.com/forge-kits/forgeapi/releases/tag/v1.5.3) - 2026-08-10

### Features

- Add SoftDeleteMixin, improve schema generator enum support, restructure README ([`99e6569`](https://github.com/forge-kits/forgeapi/commit/99e6569))

## [1.5.2](https://github.com/forge-kits/forgeapi/releases/tag/v1.5.2) - 2026-08-09

### Fixes

- **permissions:** Use pk= instead of id= for user lookup ([`2e5313a`](https://github.com/forge-kits/forgeapi/commit/2e5313a))
- **guard:** Use pk= instead of id= for model lookup ([`654f8ed`](https://github.com/forge-kits/forgeapi/commit/654f8ed))
- Use server local time in Time.now(), lock rows in scheduler/queue chore: add PR and issue templates ([`058b0a9`](https://github.com/forge-kits/forgeapi/commit/058b0a9))

## [1.5.1](https://github.com/forge-kits/forgeapi/releases/tag/v1.5.1) - 2026-07-28

### Documentation

- Update README pagination section for v1.5.0 queryset API ([`ef6b1a3`](https://github.com/forge-kits/forgeapi/commit/ef6b1a3))

## [1.5.0](https://github.com/forge-kits/forgeapi/releases/tag/v1.5.0) - 2026-07-28

### Features

- Replace Paginator DI with Laravel-style queryset pagination ([`d1f535c`](https://github.com/forge-kits/forgeapi/commit/d1f535c))

## [1.4.2](https://github.com/forge-kits/forgeapi/releases/tag/v1.4.2) - 2026-07-28

### Fixes

- Replace lambda default in FailedJob.uuid with UUIDField + pre_save signal ([`91bf058`](https://github.com/forge-kits/forgeapi/commit/91bf058))
- Replace deprecated add_event_handler with app.router.on_startup/on_shutdown ([`e6e2dc6`](https://github.com/forge-kits/forgeapi/commit/e6e2dc6))

## [1.4.1](https://github.com/forge-kits/forgeapi/releases/tag/v1.4.1) - 2026-07-28

### Features

- Add lifespan providers for broadcast, scheduler and queue; fix debug logging scope ([`e12e9b9`](https://github.com/forge-kits/forgeapi/commit/e12e9b9))

## [1.4.0](https://github.com/forge-kits/forgeapi/releases/tag/v1.4.0) - 2026-07-28

### Features

- Add mcp:install / mcp:remove / mcp:status CLI commands ([`ad4ff3a`](https://github.com/forge-kits/forgeapi/commit/ad4ff3a))

### Fixes

- Mcp commands use claude mcp add/remove instead of manual JSON write ([`edcf178`](https://github.com/forge-kits/forgeapi/commit/edcf178))

### Documentation

- Update MCP setup instructions with correct scope flags and forgeapi mcp:install ([`c0c67ed`](https://github.com/forge-kits/forgeapi/commit/c0c67ed))

### Other

- Update docs mcp, readme.md ([`d319a4f`](https://github.com/forge-kits/forgeapi/commit/d319a4f))

## [1.3.2](https://github.com/forge-kits/forgeapi/releases/tag/v1.3.2) - 2026-07-25

### Features

- Add allow_credentials to http config template ([`37bc1d0`](https://github.com/forge-kits/forgeapi/commit/37bc1d0))
- Add cors_allow_credentials config and extend Telescope with broadcast/cache hooks ([`e9987cf`](https://github.com/forge-kits/forgeapi/commit/e9987cf))
- Remove JWT, add queue system, fix CORS credentials ([`b06dffd`](https://github.com/forge-kits/forgeapi/commit/b06dffd))
- Replace EventBus with BroadcastManager (Redis Streams + Pub/Sub) ([`09c1142`](https://github.com/forge-kits/forgeapi/commit/09c1142))
- Add Storage, ImageProcessor, Scheduler, Query Scopes, Model Observers ([`eb4d879`](https://github.com/forge-kits/forgeapi/commit/eb4d879))
- Cache, support, MCP docs, policies_dir, critical bug fixes ([`6e4f239`](https://github.com/forge-kits/forgeapi/commit/6e4f239))
- **policies:** Add Policy + Gate system ([`170e69b`](https://github.com/forge-kits/forgeapi/commit/170e69b))
- Laravel-style refactor — Guards, cursor pagination, ModelMixin, Logger ([`5a3510b`](https://github.com/forge-kits/forgeapi/commit/5a3510b))
- **mcp:** Expand MCP server with full project scan and optimized docs ([`7dc021f`](https://github.com/forge-kits/forgeapi/commit/7dc021f))
- Add forge-kits MCP server ([`6d09b95`](https://github.com/forge-kits/forgeapi/commit/6d09b95))
- Add Redis Streams support with redis_type/namespace ClassVars ([`5e821b2`](https://github.com/forge-kits/forgeapi/commit/5e821b2))
- Add test suite (108 tests across 8 modules) ([`4e6a94a`](https://github.com/forge-kits/forgeapi/commit/4e6a94a))
- Add RedisBus, Redis pub/sub for EventBus, and hardening fixes ([`3fd5fa2`](https://github.com/forge-kits/forgeapi/commit/3fd5fa2))
- Bump to v0.1.6 ([`d5c2ed6`](https://github.com/forge-kits/forgeapi/commit/d5c2ed6))
- Add full-asyncpg, full-aiosqlite, full-aiomysql extras ([`4b74a30`](https://github.com/forge-kits/forgeapi/commit/4b74a30))
- Add db:fresh --force, with_role/without_role, cross-platform fixes, bump to v0.1.4 ([`c4bcee3`](https://github.com/forge-kits/forgeapi/commit/c4bcee3))
- Add Telescope dev tool, permissions, controllers, exceptions and CLI improvements ([`1c7d84b`](https://github.com/forge-kits/forgeapi/commit/1c7d84b))
- Add debug mode, multi-token BOT_TOKEN support, and loggers across all components ([`6d29c24`](https://github.com/forge-kits/forgeapi/commit/6d29c24))

### Fixes

- **lint:** Remove unused asyncio and Any imports ([`656ae33`](https://github.com/forge-kits/forgeapi/commit/656ae33))
- **lint:** Remove unused imports and fix E402 import order ([`6a143aa`](https://github.com/forge-kits/forgeapi/commit/6a143aa))
- Replace pubsub.listen() with get_message polling in EventBus ([`2405164`](https://github.com/forge-kits/forgeapi/commit/2405164))
- Fix RedisBus idle timeout and add connection resilience ([`bb96aa6`](https://github.com/forge-kits/forgeapi/commit/bb96aa6))
- Remove unused os import in seeder.py ([`f47549b`](https://github.com/forge-kits/forgeapi/commit/f47549b))
- Eliminate all pytest warnings (deprecations, insecure keys, collection) ([`e08cf0a`](https://github.com/forge-kits/forgeapi/commit/e08cf0a))
- Permission mixin, fix: auth HMAC ([`64320c2`](https://github.com/forge-kits/forgeapi/commit/64320c2))
- Remove extraneous f-prefix from string literal (ruff F541) ([`30fae22`](https://github.com/forge-kits/forgeapi/commit/30fae22))
- Correct package name in full extra (forge-kits, not forgeapi) ([`82b7bf7`](https://github.com/forge-kits/forgeapi/commit/82b7bf7))
- Resolve tortoise binary lookup on Windows, bump to v0.1.3 ([`11c98ab`](https://github.com/forge-kits/forgeapi/commit/11c98ab))
- Correct package name in ImportError messages (forge-kits, not forgeapi) ([`70d7b59`](https://github.com/forge-kits/forgeapi/commit/70d7b59))

### Refactoring

- Extract _run_seeder helper and add __init__-based seed execution ([`405db70`](https://github.com/forge-kits/forgeapi/commit/405db70))

### Documentation

- Add optional dependencies table and MCP server section to README ([`eb63fa6`](https://github.com/forge-kits/forgeapi/commit/eb63fa6))
- Clarify controller auto-prefix separator rule ([`1e83062`](https://github.com/forge-kits/forgeapi/commit/1e83062))
- Fix controller auto-prefix and base_prefix documentation ([`3a35fd7`](https://github.com/forge-kits/forgeapi/commit/3a35fd7))
- Add Seeders section to README, bump to v0.1.5 ([`a6cab68`](https://github.com/forge-kits/forgeapi/commit/a6cab68))

### Maintenance

- Prepare 1.3.2 ([`24358ba`](https://github.com/forge-kits/forgeapi/commit/24358ba))

### Other

- Prepare build 1.2.1 ([`46fbc97`](https://github.com/forge-kits/forgeapi/commit/46fbc97))
- Prepare build 1.2.0 ([`f06899a`](https://github.com/forge-kits/forgeapi/commit/f06899a))
- V0.1.1 ([`aa649ad`](https://github.com/forge-kits/forgeapi/commit/aa649ad))
- Fix workflow ([`03a013c`](https://github.com/forge-kits/forgeapi/commit/03a013c))
- Fix lint ([`dfe4c3b`](https://github.com/forge-kits/forgeapi/commit/dfe4c3b))
- Upload workflow ([`3f2f4d7`](https://github.com/forge-kits/forgeapi/commit/3f2f4d7))
- Upload ([`f841175`](https://github.com/forge-kits/forgeapi/commit/f841175))
- Init ([`b7be858`](https://github.com/forge-kits/forgeapi/commit/b7be858))

## [1.3.1](https://github.com/forge-kits/forgeapi/releases/tag/v1.3.1) - 2026-07-21

### Features

- Add Storage, ImageProcessor, Scheduler, Query Scopes, Model Observers ([`1d6c33d`](https://github.com/forge-kits/forgeapi/commit/1d6c33d))

## [1.2.1](https://github.com/forge-kits/forgeapi/releases/tag/v1.2.1) - 2026-07-17

### Other

- Prepare build 1.2.1 ([`039d919`](https://github.com/forge-kits/forgeapi/commit/039d919))

## [1.2.0](https://github.com/forge-kits/forgeapi/releases/tag/v1.2.0) - 2026-07-14

### Features

- Cache, support, MCP docs, policies_dir, critical bug fixes ([`7b74fd0`](https://github.com/forge-kits/forgeapi/commit/7b74fd0))
- **policies:** Add Policy + Gate system ([`8577ffd`](https://github.com/forge-kits/forgeapi/commit/8577ffd))
- Laravel-style refactor — Guards, cursor pagination, ModelMixin, Logger ([`336b348`](https://github.com/forge-kits/forgeapi/commit/336b348))

### Fixes

- **lint:** Remove unused asyncio and Any imports ([`ff70e8e`](https://github.com/forge-kits/forgeapi/commit/ff70e8e))
- **lint:** Remove unused imports and fix E402 import order ([`7f696f3`](https://github.com/forge-kits/forgeapi/commit/7f696f3))

### Other

- Prepare build 1.2.0 ([`df188fd`](https://github.com/forge-kits/forgeapi/commit/df188fd))

## [1.1.0](https://github.com/forge-kits/forgeapi/releases/tag/v1.1.0) - 2026-07-13

### Features

- **mcp:** Expand MCP server with full project scan and optimized docs ([`87bd5d2`](https://github.com/forge-kits/forgeapi/commit/87bd5d2))

### Documentation

- Add optional dependencies table and MCP server section to README ([`611c3ec`](https://github.com/forge-kits/forgeapi/commit/611c3ec))

## [1.0.0](https://github.com/forge-kits/forgeapi/releases/tag/v1.0.0) - 2026-07-13

### Features

- Add forge-kits MCP server ([`cb41376`](https://github.com/forge-kits/forgeapi/commit/cb41376))

## [0.2.9](https://github.com/forge-kits/forgeapi/releases/tag/v0.2.9) - 2026-07-13

### Fixes

- Replace pubsub.listen() with get_message polling in EventBus ([`b5eef47`](https://github.com/forge-kits/forgeapi/commit/b5eef47))

## [0.2.8](https://github.com/forge-kits/forgeapi/releases/tag/v0.2.8) - 2026-07-13

### Fixes

- Fix RedisBus idle timeout and add connection resilience ([`b7076ef`](https://github.com/forge-kits/forgeapi/commit/b7076ef))

## [0.2.7](https://github.com/forge-kits/forgeapi/releases/tag/v0.2.7) - 2026-07-09

### Features

- Add Redis Streams support with redis_type/namespace ClassVars ([`ea9432c`](https://github.com/forge-kits/forgeapi/commit/ea9432c))

## [0.2.6](https://github.com/forge-kits/forgeapi/releases/tag/v0.2.6) - 2026-07-09

### Features

- Add test suite (108 tests across 8 modules) ([`83ce9a0`](https://github.com/forge-kits/forgeapi/commit/83ce9a0))
- Add RedisBus, Redis pub/sub for EventBus, and hardening fixes ([`1ee3bd6`](https://github.com/forge-kits/forgeapi/commit/1ee3bd6))

### Fixes

- Remove unused os import in seeder.py ([`7483ba8`](https://github.com/forge-kits/forgeapi/commit/7483ba8))
- Eliminate all pytest warnings (deprecations, insecure keys, collection) ([`2d08a97`](https://github.com/forge-kits/forgeapi/commit/2d08a97))
- Permission mixin, fix: auth HMAC ([`55ac51f`](https://github.com/forge-kits/forgeapi/commit/55ac51f))
- Remove extraneous f-prefix from string literal (ruff F541) ([`b0bfa2b`](https://github.com/forge-kits/forgeapi/commit/b0bfa2b))

### Refactoring

- Extract _run_seeder helper and add __init__-based seed execution ([`e893c17`](https://github.com/forge-kits/forgeapi/commit/e893c17))

### Documentation

- Clarify controller auto-prefix separator rule ([`bee0905`](https://github.com/forge-kits/forgeapi/commit/bee0905))
- Fix controller auto-prefix and base_prefix documentation ([`6e67eee`](https://github.com/forge-kits/forgeapi/commit/6e67eee))

## [0.1.6](https://github.com/forge-kits/forgeapi/releases/tag/v0.1.6) - 2026-07-05

### Features

- Bump to v0.1.6 ([`1a57537`](https://github.com/forge-kits/forgeapi/commit/1a57537))
- Add full-asyncpg, full-aiosqlite, full-aiomysql extras ([`f384466`](https://github.com/forge-kits/forgeapi/commit/f384466))

### Fixes

- Correct package name in full extra (forge-kits, not forgeapi) ([`0748d06`](https://github.com/forge-kits/forgeapi/commit/0748d06))

## [0.1.5](https://github.com/forge-kits/forgeapi/releases/tag/v0.1.5) - 2026-07-05

### Documentation

- Add Seeders section to README, bump to v0.1.5 ([`eeb0df9`](https://github.com/forge-kits/forgeapi/commit/eeb0df9))

## [0.1.4](https://github.com/forge-kits/forgeapi/releases/tag/v0.1.4) - 2026-07-04

### Features

- Add db:fresh --force, with_role/without_role, cross-platform fixes, bump to v0.1.4 ([`a0d699c`](https://github.com/forge-kits/forgeapi/commit/a0d699c))

## [0.1.3](https://github.com/forge-kits/forgeapi/releases/tag/v0.1.3) - 2026-07-04

### Features

- Add Telescope dev tool, permissions, controllers, exceptions and CLI improvements ([`a18bfc2`](https://github.com/forge-kits/forgeapi/commit/a18bfc2))

### Fixes

- Resolve tortoise binary lookup on Windows, bump to v0.1.3 ([`4832910`](https://github.com/forge-kits/forgeapi/commit/4832910))

## [0.1.2](https://github.com/forge-kits/forgeapi/releases/tag/v0.1.2) - 2026-06-28

### Features

- Add debug mode, multi-token BOT_TOKEN support, and loggers across all components ([`1667114`](https://github.com/forge-kits/forgeapi/commit/1667114))

## [0.1.1](https://github.com/forge-kits/forgeapi/releases/tag/v0.1.1) - 2026-06-28

### Fixes

- Correct package name in ImportError messages (forge-kits, not forgeapi) ([`23b6486`](https://github.com/forge-kits/forgeapi/commit/23b6486))

### Other

- V0.1.1 ([`7f517f8`](https://github.com/forge-kits/forgeapi/commit/7f517f8))

## [0.1.0](https://github.com/forge-kits/forgeapi/releases/tag/v0.1.0) - 2026-06-26

### Other

- Fix workflow ([`bf8e074`](https://github.com/forge-kits/forgeapi/commit/bf8e074))
- Fix lint ([`02f816c`](https://github.com/forge-kits/forgeapi/commit/02f816c))
- Upload workflow ([`4f434df`](https://github.com/forge-kits/forgeapi/commit/4f434df))
- Upload ([`5b9f4ed`](https://github.com/forge-kits/forgeapi/commit/5b9f4ed))
- Init ([`24a21bd`](https://github.com/forge-kits/forgeapi/commit/24a21bd))
