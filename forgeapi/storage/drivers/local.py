from __future__ import annotations

import asyncio
from pathlib import Path

from .base import StorageDriver


class LocalDriver(StorageDriver):
    """Stores files on the local filesystem.

    Args:
        root:     Root directory for stored files. Created automatically.
        base_url: Public URL prefix returned by :meth:`url`.
    """

    def __init__(self, root: str = "storage/app", base_url: str = "/storage") -> None:
        self._root = Path(root)
        self._base_url = base_url.rstrip("/")

    def _full(self, path: str) -> Path:
        return self._root / path

    async def put(self, path: str, data: bytes) -> str:
        full = self._full(path)
        await asyncio.to_thread(full.parent.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(full.write_bytes, data)
        return path

    async def get(self, path: str) -> bytes:
        return await asyncio.to_thread(self._full(path).read_bytes)

    async def delete(self, path: str) -> bool:
        full = self._full(path)

        def _do() -> bool:
            if full.exists():
                full.unlink()
                return True
            return False

        return await asyncio.to_thread(_do)

    async def exists(self, path: str) -> bool:
        return await asyncio.to_thread(self._full(path).exists)

    async def list(self, directory: str = "") -> list[str]:
        base = self._root / directory

        def _do() -> list[str]:
            if not base.exists():
                return []
            return [
                str(f.relative_to(self._root)).replace("\\", "/")
                for f in base.rglob("*")
                if f.is_file()
            ]

        return await asyncio.to_thread(_do)

    def url(self, path: str) -> str:
        return f"{self._base_url}/{path}"
