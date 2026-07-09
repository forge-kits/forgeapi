import tomllib
from pathlib import Path
from pydantic import BaseModel, Field, ValidationError, model_validator


class ProjectConfig(BaseModel):
    name: str = "my-app"
    version: str = "0.1.0"
    description: str = ""


class StructureConfig(BaseModel):
    models_dir: str = "database/models"
    controllers_dir: str = "app/controllers"
    schemas_dir: str = "app/schemas"
    events_dir: str = "app/events"
    listeners_dir: str = "app/listeners"
    seeds_dir: str = "database/seeds"
    base_prefix: str = "/api/v1"


class AuthTomlConfig(BaseModel):
    strategy: str = "jwt"
    jwt_secret_env: str = "JWT_SECRET"
    access_ttl_minutes: int = 30
    refresh_ttl_days: int = 7
    cookie_name: str = "session"
    cookie_httponly: bool = True
    cookie_secure: bool = True


class PaginationConfig(BaseModel):
    default_limit: int = Field(20, ge=1, description="Default page size (must be >= 1)")
    max_limit: int = Field(100, ge=1, description="Maximum allowed page size (must be >= 1)")

    @model_validator(mode="after")
    def check_limits_order(self) -> "PaginationConfig":
        if self.default_limit > self.max_limit:
            raise ValueError(
                f"default_limit ({self.default_limit}) must not exceed "
                f"max_limit ({self.max_limit}). Check [pagination] in forgeapi.toml."
            )
        return self


class DatabaseConfig(BaseModel):
    tortoise_orm: str = "app.config.TORTOISE_ORM"


class KitConfig(BaseModel):
    project: ProjectConfig = ProjectConfig()
    structure: StructureConfig = StructureConfig()
    auth: AuthTomlConfig = AuthTomlConfig()
    pagination: PaginationConfig = PaginationConfig()
    database: DatabaseConfig = DatabaseConfig()


def load_config(path: str = "forgeapi.toml") -> KitConfig:
    from .exceptions import ForgeAPIConfigError

    config_path = Path(path)
    if not config_path.exists():
        return KitConfig()

    with open(config_path, "rb") as f:
        raw = tomllib.load(f)

    try:
        return KitConfig(
            project=raw.get("project", {}),
            structure=raw.get("structure", {}),
            auth=raw.get("auth", {}),
            pagination=raw.get("pagination", {}),
            database=raw.get("database", {}),
        )
    except ValidationError as exc:
        raise ForgeAPIConfigError(
            f"Invalid configuration in '{path}': {exc}",
            hint="Check your forgeapi.toml for incorrect types or missing required fields.",
        ) from exc
