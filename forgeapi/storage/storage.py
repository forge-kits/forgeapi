from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .drivers.base import StorageDriver


class _Storage:
    """Facade for file storage — delegates to the configured driver.

    Configure once at startup::

        from forgeapi import Storage

        Storage.configure(driver="local", root="storage/app", base_url="/storage")
        # or S3:
        Storage.configure(
            driver="s3",
            bucket="my-bucket",
            region="eu-central-1",
            access_key="...",
            secret_key="...",
        )

    Then use anywhere::

        path = await Storage.put("avatars/user_1.jpg", file_bytes)
        data = await Storage.get("avatars/user_1.jpg")
        url  = Storage.url("avatars/user_1.jpg")
        ok   = await Storage.delete("avatars/user_1.jpg")

    Multiple disks::

        Storage.add_disk("s3", S3Driver(bucket="assets", ...))
        await Storage.disk("s3").put("file.png", data)
    """

    def __init__(self) -> None:
        self._driver: "StorageDriver | None" = None
        self._disks: dict[str, "StorageDriver"] = {}

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    def configure(self, driver: str = "local", **kwargs) -> None:
        """Set the default driver.

        Args:
            driver: ``"local"`` or ``"s3"``.
            **kwargs: Passed directly to the driver constructor.
        """
        self._driver = self._make(driver, **kwargs)

    def add_disk(self, name: str, driver: "StorageDriver") -> None:
        """Register a named disk for use with :meth:`disk`."""
        self._disks[name] = driver

    def disk(self, name: str) -> "StorageDriver":
        """Return a named disk driver.

        Raises:
            KeyError: If *name* was not registered via :meth:`add_disk`.
        """
        if name not in self._disks:
            raise KeyError(
                f"Storage disk '{name}' is not configured. "
                "Register it with Storage.add_disk(name, driver)."
            )
        return self._disks[name]

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @property
    def _backend(self) -> "StorageDriver":
        if self._driver is None:
            from .drivers.local import LocalDriver
            self._driver = LocalDriver()
        return self._driver

    @staticmethod
    def _make(driver: str, **kwargs) -> "StorageDriver":
        if driver == "local":
            from .drivers.local import LocalDriver
            return LocalDriver(**kwargs)
        if driver == "s3":
            from .drivers.s3 import S3Driver
            return S3Driver(**kwargs)
        raise ValueError(
            f"Unknown storage driver '{driver}'. Valid options: 'local', 's3'."
        )

    # ------------------------------------------------------------------
    # Operations (delegate to default driver)
    # ------------------------------------------------------------------

    async def put(self, path: str, data: bytes) -> str:
        """Write *data* to *path* and return the stored path."""
        return await self._backend.put(path, data)

    async def get(self, path: str) -> bytes:
        """Read and return the file at *path*."""
        return await self._backend.get(path)

    async def delete(self, path: str) -> bool:
        """Delete *path*. Returns ``True`` if the file existed."""
        return await self._backend.delete(path)

    async def exists(self, path: str) -> bool:
        """Return ``True`` if *path* exists in storage."""
        return await self._backend.exists(path)

    async def missing(self, path: str) -> bool:
        """Return ``True`` if *path* does NOT exist."""
        return not await self.exists(path)

    async def list(self, directory: str = "") -> list[str]:
        """List all files under *directory* (recursive)."""
        return await self._backend.list(directory)

    def url(self, path: str) -> str:
        """Return the public URL for *path*."""
        return self._backend.url(path)


Storage = _Storage()
