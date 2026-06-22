from pydantic_settings import BaseSettings, SettingsConfigDict


class BaseAppSettings(BaseSettings):
    """Base application settings backed by environment variables and ``.env``.

    Inherit and add your own fields.  Values are read from the environment
    first, then from a ``.env`` file in the working directory::

        from forgeapi.settings import BaseAppSettings

        class Settings(BaseAppSettings):
            database_url: str
            redis_url: str | None = None
            jwt_secret: str
            debug: bool = False

        settings = Settings()   # reads .env automatically
    """

    debug: bool = False
    app_name: str = "FastAPI App"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )
