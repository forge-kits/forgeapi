from forgeapi.foundation import Provider
from forgeapi.logging import log

_log = log.channel("storage.provider")


class StorageProvider(Provider):
    """Configures the :class:`~forgeapi.storage.storage.Storage` facade.

    Reads from ``config/storage.py``::

        config = {
            "driver": "local",        # "local" | "s3"
            "root": "storage/app",
            "base_url": "/storage",
            # S3:
            # "bucket": "my-bucket",
            # "region": "us-east-1",
            # "access_key": env("AWS_ACCESS_KEY_ID"),
            # "secret_key": env("AWS_SECRET_ACCESS_KEY"),
            # "endpoint_url": "",
        }
    """

    def register(self) -> None:
        from . import Storage
        cfg = self.config.storage
        if cfg.driver == "s3":
            kwargs = dict(
                bucket=cfg.bucket,
                region=cfg.region,
                access_key=cfg.access_key,
                secret_key=cfg.secret_key,
            )
            if cfg.endpoint_url:
                kwargs["endpoint_url"] = cfg.endpoint_url
            if cfg.acl:
                kwargs["acl"] = cfg.acl
        else:
            kwargs = dict(root=cfg.root, base_url=cfg.base_url)
        Storage.configure(driver=cfg.driver, **kwargs)
        _log.debug("Storage: driver=%s", cfg.driver)
