from typing import Any

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, model_validator


class ProjectConfig(BaseModel):
    name: str = "my-app"
    version: str = "0.1.0"
    description: str = ""
    #: Enables Telescope. Set via env: ``"debug": env("APP_DEBUG", False)``.
    #: Never enable in production.
    debug: bool = False
    #: Extra Provider classes to run after the built-in ones —
    #: Laravel ``config/app.php`` ``providers`` equivalent.
    providers: list[Any] = []


class HttpConfig(BaseModel):
    """The ``http`` config section — global middleware stack (``config/http.py``).

    ::

        config = {
            "cors": ["*"],       # True → all origins; list → specific; False → off
            "rate_limit": 60,    # req/min per IP; True → 60; False → off
            "request_id": True,  # inject X-Request-ID header
            "access_log": True,  # log method/path/status/duration per request
            "middleware": [],    # custom classes or (cls, kwargs) tuples
        }
    """

    cors: bool | list[str] = False
    rate_limit: bool | int = False
    request_id: bool = False
    access_log: bool = True
    middleware: list[Any] = []


class StructureConfig(BaseModel):
    models_dir: str = "database/models"
    controllers_dir: str = "app/controllers"
    schemas_dir: str = "app/schemas"
    events_dir: str = "app/events"
    listeners_dir: str = "app/listeners"
    policies_dir: str = "app/policies"
    seeds_dir: str = "database/seeds"
    base_prefix: str = "/api/v1"


class AuthConfig(BaseModel):
    """The ``auth`` config section — named guards (``config/auth.py``)::

        config = {
            "default": "api",
            "guards": {
                "api":   {"strategy": "jwt", "secret": env("JWT_SECRET"),
                          "model": "database.models.user.User"},
                "admin": {"strategy": "jwt", "secret": env("ADMIN_JWT_SECRET"),
                          "model": "database.models.admin.Admin"},
            },
        }

    Guard dict keys: ``strategy`` (jwt | cookie | telegram | custom name
    registered via ``auth.extend()``), optional ``model`` (dotted path to the
    user model), plus the strategy's ``from_config`` keys.
    """

    default: str = "api"
    guards: dict[str, dict] = {}


class PaginationConfig(BaseModel):
    default_limit: int = Field(20, ge=1, description="Default page size (must be >= 1)")
    max_limit: int = Field(100, ge=1, description="Maximum allowed page size (must be >= 1)")

    @model_validator(mode="after")
    def check_limits_order(self) -> "PaginationConfig":
        if self.default_limit > self.max_limit:
            raise ValueError(
                f"default_limit ({self.default_limit}) must not exceed "
                f"max_limit ({self.max_limit}). Check the pagination config section."
            )
        return self


class DatabaseConfig(BaseModel):
    """The ``database`` config section (``config/database.py``).

    The file only needs to define the ``TORTOISE_ORM`` dict (connections,
    apps, migrations) — the loader derives the dotted import path the
    tortoise CLI needs from the file location (``config/`` is a namespace
    package, so the path is importable)::

        TORTOISE_ORM = {"connections": {...}, "apps": {...}}

    An explicit ``config`` dict is only needed when the ORM dict lives
    somewhere else::

        config = {"tortoise_orm": "app.settings.TORTOISE_ORM"}
    """

    tortoise_orm: str = "config.database.TORTOISE_ORM"


class CacheConfig(BaseModel):
    driver: str = "memory"
    prefix: str = ""
    ttl: int | None = None
    redis_url: str = "redis://localhost:6379/0"


class KitConfig(BaseModel):
    """Validated application config.

    Known sections are typed models; unknown sections (e.g. a custom
    ``config/services.py``) are kept as raw dicts and reachable via
    :meth:`get`.
    """

    model_config = ConfigDict(extra="allow")

    project: ProjectConfig = ProjectConfig()
    structure: StructureConfig = StructureConfig()
    http: HttpConfig = HttpConfig()
    auth: AuthConfig = AuthConfig()
    pagination: PaginationConfig = PaginationConfig()
    database: DatabaseConfig = DatabaseConfig()
    cache: CacheConfig = CacheConfig()

    # section names the user actually provided (vs. pure defaults) —
    # feature enablement is decided by presence, e.g. auth boots only
    # when an "auth" section exists in the project config.
    _provided: set = PrivateAttr(default_factory=set)

    def provided(self, section: str) -> bool:
        """``True`` when *section* came from the user's config, not defaults."""
        return section in self._provided

    def get(self, key: str, default: Any = None) -> Any:
        """Dot-notation access — Laravel ``config('auth.default')`` equivalent.

        Works for typed sections and custom ones alike::

            cfg.get("auth.guards.api.strategy")
            cfg.get("services.stripe.key", default="")
        """
        node: Any = self
        for part in key.split("."):
            if isinstance(node, BaseModel):
                if part in type(node).model_fields:
                    node = getattr(node, part)
                elif node.model_extra and part in node.model_extra:
                    node = node.model_extra[part]
                else:
                    return default
            elif isinstance(node, dict) and part in node:
                node = node[part]
            else:
                return default
        return node
