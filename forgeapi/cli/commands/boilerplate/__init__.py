from __future__ import annotations

from pathlib import Path


def run(root: Path, strategy: str) -> None:
    from . import shared
    from . import telegram as tg

    is_telegram = strategy == "telegram"

    # ── Shared (all strategies) ───────────────────────────────────────────────
    _write(root / "database/models/__init__.py",      shared._MODELS_INIT)
    _write(root / "database/models/post.py",          shared._MODEL_POST)
    _write(root / "app/schemas/__init__.py",          "")
    _write(root / "app/schemas/post.py",              shared._SCHEMA_POST)
    _write(root / "app/events/post_created_event.py", shared._EVENT_POST_CREATED)
    _write(root / "app/listeners/post_listener.py",   shared._LISTENER_POST)
    _write(root / "database/seeds/post_seeder.py",    shared._SEEDER_POST)
    _write(root / "database/seeds/__init__.py",       shared._SEEDS_INIT)
    _write(root / "app/bus.py",                       shared._BUS_EXAMPLE)

    if is_telegram:
        _write(root / "database/models/user.py",              tg._MODEL_USER)
        _write(root / "app/schemas/user.py",                  tg._SCHEMA_USER)
        _write(root / "app/events/user_first_login_event.py", tg._EVENT_USER_FIRST_LOGIN)
        _write(root / "app/events/__init__.py",               tg._EVENTS_INIT)
        _write(root / "app/listeners/user_listener.py",       tg._LISTENER_USER)
        _write(root / "app/controllers/user_controller.py",   tg._CONTROLLER_USER)
        _write(root / "app/controllers/post_controller.py",   tg._CONTROLLER_POST)
        _write(root / "database/seeds/user_seeder.py",        tg._SEEDER_USER)
    else:
        _write(root / "database/models/user.py",              shared._MODEL_USER_PASSWORD)
        _write(root / "app/events/user_registered_event.py",  shared._EVENT_USER_REGISTERED)
        _write(root / "app/events/__init__.py",               shared._EVENTS_INIT_PASSWORD)
        _write(root / "app/listeners/user_listener.py",       shared._LISTENER_USER_PASSWORD)
        _write(root / "app/policies/__init__.py",             "")
        _write(root / "app/policies/post_policy.py",          shared._POST_POLICY)
        _write(root / "app/controllers/post_controller.py",   shared._CONTROLLER_POST_STD)
        _write(root / "database/seeds/user_seeder.py",        shared._SEEDER_USER_PASSWORD)

        if strategy == "jwt":
            from . import jwt as jwt_mod
            _write(root / "app/schemas/user.py",                jwt_mod._SCHEMA_USER)
            _write(root / "app/controllers/user_controller.py", jwt_mod._CONTROLLER_USER)
        else:  # cookie
            from . import cookie as cookie_mod
            _write(root / "app/schemas/user.py",                cookie_mod._SCHEMA_USER)
            _write(root / "app/controllers/user_controller.py", cookie_mod._CONTROLLER_USER)

    _print_summary(root, strategy)


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _print_summary(root: Path, strategy: str) -> None:
    import typer

    n = root.name
    typer.echo("")
    typer.echo(f"  Welcome project ready  (strategy: {strategy})")
    typer.echo("")
    typer.echo("  Run:")
    typer.echo(f"    cd {n}")
    typer.echo("    forgeapi db:init && forgeapi db:makemigrations && forgeapi db:migrate")
    typer.echo("    forgeapi db:seed")
    typer.echo("    forgeapi runserver --reload")
    typer.echo("")
    typer.echo("  Endpoints:")

    if strategy == "telegram":
        typer.echo("    GET    /api/v1/users/me         — auto-register + current user (X-Telegram-Init-Data)")
        typer.echo("    GET    /api/v1/users/           — list users")
    else:
        typer.echo("    POST   /api/v1/users/register   — register" + (" → JWT tokens" if strategy == "jwt" else " → sets cookie"))
        typer.echo("    POST   /api/v1/users/login      — login" + (" → JWT tokens" if strategy == "jwt" else " → sets cookie"))
        if strategy == "jwt":
            typer.echo("    POST   /api/v1/users/refresh    — refresh access token")
        if strategy == "cookie":
            typer.echo("    POST   /api/v1/users/logout     — logout (clears cookie)")
        typer.echo("    GET    /api/v1/users/me         — current user (auth required)")
        typer.echo("    GET    /api/v1/users/           — list users (admin only)")

    typer.echo("    GET    /api/v1/posts/           — list published posts (paginated)")
    typer.echo("    GET    /api/v1/posts/popular    — top-10 posts (Cache, 5 min TTL)")
    typer.echo("    POST   /api/v1/posts/           — create post (auth + policy)")
    typer.echo("    GET    /api/v1/posts/{id}       — get post (policy: view)")
    typer.echo("    PATCH  /api/v1/posts/{id}       — update own post (policy: update)")
    typer.echo("    DELETE /api/v1/posts/{id}       — delete own post (policy: delete)")
    typer.echo("")
    typer.echo("  Seed accounts:")
    if strategy != "telegram":
        typer.echo("    admin / admin123  (role: admin — full access)")
        typer.echo("    user  / user123   (role: user  — create posts)")
    else:
        typer.echo("    demo_user  telegram_id=123456789")
    typer.echo("")
    typer.echo("  Key files:")
    typer.echo("    app/policies/post_policy.py   — PostPolicy (gate)")
    typer.echo("    app/controllers/post_controller.py  — Cache + gate + ModelMixin")
    typer.echo("    app/events/post_created_event.py    — event (Redis comments)")
    typer.echo("    app/listeners/post_listener.py      — @listen handler")
    typer.echo("    app/bus.py                          — RedisBus cross-service example")
    if strategy != "telegram":
        typer.echo("    database/seeds/user_seeder.py       — roles + permissions setup")
