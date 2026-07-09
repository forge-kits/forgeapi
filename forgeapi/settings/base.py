from pydantic_settings import BaseSettings, SettingsConfigDict

_SENSITIVE_KEYWORDS = frozenset({"secret", "password", "token", "key", "auth", "credential"})


class BaseAppSettings(BaseSettings):
    """Base application settings backed by environment variables and ``.env``.

    Inherit and add your own fields.  Values are read from the environment
    first, then from a ``.env`` file in the working directory.

    Fields whose names contain ``secret``, ``password``, ``token``, ``key``,
    ``auth``, or ``credential`` are automatically masked in ``__repr__`` /
    ``__str__`` so they never appear in log output::

        from forgeapi.settings import BaseAppSettings

        class Settings(BaseAppSettings):
            database_url: str
            redis_url: str | None = None
            jwt_secret: str       # masked in repr
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

    def __repr__(self) -> str:
        fields = []
        for name in self.__class__.model_fields:
            value = getattr(self, name, None)
            if any(kw in name.lower() for kw in _SENSITIVE_KEYWORDS):
                fields.append(f"{name}='***'")
            else:
                fields.append(f"{name}={value!r}")
        return f"{self.__class__.__name__}({', '.join(fields)})"

    def __str__(self) -> str:
        return self.__repr__()
