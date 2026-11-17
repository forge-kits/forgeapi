from __future__ import annotations

import json
from datetime import timedelta
from typing import Any

from tortoise import timezone
from tortoise.exceptions import IntegrityError
from tortoise.transactions import in_transaction

from forgeapi.exceptions import ForgeAPIConfigError

from ..models import CacheEntry
from .base import CacheDriver


class DatabaseDriver(CacheDriver):
    """Cache stored in the ``cache`` table of the default Tortoise connection.

    Values are JSON-serialised, like the Redis driver.  Expired rows are
    removed lazily on access; call :meth:`prune` (e.g. from a scheduled task)
    to purge the ones nobody reads again.
    """

    @staticmethod
    def _ready() -> None:
        if CacheEntry._meta.default_connection is None:
            raise ForgeAPIConfigError(
                "The database cache driver needs the cache table.",
                hint=(
                    'Add "forgeapi.cache.models" to the models list in config/database.py '
                    "and create the table, or set the cache driver to \"redis\"."
                ),
            )

    @staticmethod
    def _expired(entry: CacheEntry) -> bool:
        return entry.expires_at is not None and entry.expires_at <= timezone.now()

    async def _entry(self, key: str) -> CacheEntry | None:
        """The live row for *key*; an expired row is deleted and reported as missing."""
        self._ready()
        entry = await CacheEntry.get_or_none(key=key)
        if entry is not None and self._expired(entry):
            await CacheEntry.filter(key=key).delete()
            return None
        return entry

    async def get(self, key: str) -> Any:
        entry = await self._entry(key)
        return None if entry is None else json.loads(entry.value)

    async def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        self._ready()
        expires_at = timezone.now() + timedelta(seconds=ttl) if ttl is not None else None
        await CacheEntry.update_or_create(
            key=key,
            defaults={"value": json.dumps(value, default=str), "expires_at": expires_at},
        )

    async def forget(self, key: str) -> bool:
        entry = await self._entry(key)
        if entry is None:
            return False
        await CacheEntry.filter(key=key).delete()
        return True

    async def flush(self) -> None:
        self._ready()
        await CacheEntry.all().delete()

    async def has(self, key: str) -> bool:
        return await self._entry(key) is not None

    async def increment(self, key: str, amount: int = 1) -> int:
        self._ready()
        # a concurrent first write can hit the primary key; the retry then
        # finds the row and takes the locked-update path
        for attempt in (1, 2):
            try:
                async with in_transaction() as conn:
                    entry = await CacheEntry.filter(key=key).using_db(conn).select_for_update().first()
                    if entry is None or self._expired(entry):
                        new_value = amount
                        expires_at = None
                    else:
                        new_value = int(json.loads(entry.value)) + amount
                        expires_at = entry.expires_at
                    await CacheEntry.update_or_create(
                        key=key,
                        defaults={"value": json.dumps(new_value), "expires_at": expires_at},
                        using_db=conn,
                    )
                    return new_value
            except IntegrityError:
                if attempt == 2:
                    raise
        raise AssertionError("unreachable")

    async def decrement(self, key: str, amount: int = 1) -> int:
        return await self.increment(key, -amount)

    async def prune(self) -> int:
        """Delete every expired row.  Returns how many were removed."""
        self._ready()
        return await CacheEntry.filter(expires_at__lte=timezone.now()).delete()
