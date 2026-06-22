import tomllib
from pathlib import Path
from typing import Optional
from pydantic import BaseModel


class ProjectConfig(BaseModel):
    name: str = "my-app"
    version: str = "0.1.0"


class StructureConfig(BaseModel):
    models_dir: str = "app/models"
    controllers_dir: str = "app/controllers"
    schemas_dir: str = "app/schemas"
    events_dir: str = "app/events"
    listeners_dir: str = "app/listeners"
    base_prefix: str = "/api/v1"


class AuthTomlConfig(BaseModel):
    strategy: str = "jwt"
    jwt_secret_env: str = "JWT_SECRET"
    access_ttl_minutes: int = 30
    refresh_ttl_days: int = 7
    cookie_name: str = "session"
    cookie_httponly: bool = True
    cookie_secure: bool = False


class PaginationConfig(BaseModel):
    default_limit: int = 20
    max_limit: int = 100


class DatabaseConfig(BaseModel):
    tortoise_orm: str = "app.config.TORTOISE_ORM"


class KitConfig(BaseModel):
    project: ProjectConfig = ProjectConfig()
    structure: StructureConfig = StructureConfig()
    auth: AuthTomlConfig = AuthTomlConfig()
    pagination: PaginationConfig = PaginationConfig()
    database: DatabaseConfig = DatabaseConfig()


def load_config(path: str = "forgeapi.toml") -> KitConfig:
    config_path = Path(path)
    if not config_path.exists():
        return KitConfig()

    with open(config_path, "rb") as f:
        raw = tomllib.load(f)

    return KitConfig(
        project=raw.get("project", {}),
        structure=raw.get("structure", {}),
        auth=raw.get("auth", {}),
        pagination=raw.get("pagination", {}),
        database=raw.get("database", {}),
    )
