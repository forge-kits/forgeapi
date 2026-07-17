from forgeapi.foundation import Provider
from forgeapi.logging import log

_log = log.channel("cache.provider")


class CacheProvider(Provider):
    """Configures the :class:`~forgeapi.cache.cache.Cache` facade.

    Runs in the register phase so user code imported during boot (controllers,
    listeners) already sees the configured driver.
    """

    def register(self) -> None:
        from . import Cache
        cfg = self.config.cache
        Cache.configure(
            driver=cfg.driver,
            prefix=cfg.prefix,
            ttl=cfg.ttl,
            redis_url=cfg.redis_url,
        )
        _log.debug("Cache: driver=%s prefix=%r", cfg.driver, cfg.prefix)
