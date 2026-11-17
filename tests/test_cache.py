"""Cache facade on the database driver (the default)."""
import asyncio

import pytest
from tortoise import Tortoise
import tortoise.timezone as tt

from forgeapi.cache import Cache, DatabaseDriver
from forgeapi.cache.cache import _Cache
from forgeapi.cache.models import CacheEntry
from forgeapi.config.models import CacheConfig
from forgeapi.exceptions import ForgeAPIConfigError


@pytest.fixture
async def cache():
    await Tortoise.init(
        db_url="sqlite://:memory:",
        modules={"models": ["forgeapi.cache.models"]},
    )
    await Tortoise.generate_schemas()
    c = _Cache()
    c.configure(driver="database")
    yield c
    await Tortoise.close_connections()
    tt._reset_timezone_cache()


def test_default_driver_is_database():
    assert CacheConfig().driver == "database"
    c = _Cache()
    c.configure()
    assert isinstance(c._backend, DatabaseDriver)
    assert isinstance(_Cache()._backend, DatabaseDriver)


def test_unknown_driver_raises():
    with pytest.raises(ForgeAPIConfigError):
        _Cache().configure(driver="memory")


async def test_set_get_roundtrip(cache):
    await cache.set("k", {"a": [1, 2], "b": "x"})
    assert await cache.get("k") == {"a": [1, 2], "b": "x"}
    assert await cache.get("missing", default="d") == "d"


async def test_overwrite(cache):
    await cache.set("k", 1)
    await cache.set("k", 2)
    assert await cache.get("k") == 2
    assert await CacheEntry.all().count() == 1


async def test_ttl_expiry_deletes_row(cache):
    await cache.set("k", 1, ttl=1)
    assert await cache.has("k")
    await asyncio.sleep(1.1)
    assert await cache.get("k") is None
    assert await CacheEntry.all().count() == 0


async def test_forever_and_default_ttl(cache):
    cache._default_ttl = 1
    await cache.forever("f", 1)
    await cache.set("d", 1)
    await asyncio.sleep(1.1)
    assert await cache.get("f") == 1
    assert await cache.get("d") is None


async def test_forget_has_missing_pull(cache):
    await cache.set("k", "v")
    assert await cache.missing("k") is False
    assert await cache.pull("k") == "v"
    assert await cache.has("k") is False
    assert await cache.forget("k") is False
    await cache.set("k", "v")
    assert await cache.forget("k") is True


async def test_expired_forget_returns_false(cache):
    await cache.set("k", 1, ttl=1)
    await asyncio.sleep(1.1)
    assert await cache.forget("k") is False


async def test_flush(cache):
    await cache.set("a", 1)
    await cache.set("b", 2)
    await cache.flush()
    assert await CacheEntry.all().count() == 0


async def test_prefix(cache):
    cache.configure(driver="database", prefix="app:")
    await cache.set("k", 1)
    assert await CacheEntry.filter(key="app:k").exists()


async def test_remember_computes_once(cache):
    calls = []

    async def compute():
        calls.append(1)
        return 42

    assert await cache.remember("r", compute) == 42
    assert await cache.remember("r", compute) == 42
    assert calls == [1]


async def test_increment_decrement(cache):
    assert await cache.increment("n") == 1
    assert await cache.increment("n", 5) == 6
    assert await cache.decrement("n", 2) == 4
    assert await cache.get("n") == 4


async def test_increment_keeps_ttl(cache):
    await cache.set("n", 1, ttl=60)
    await cache.increment("n")
    entry = await CacheEntry.get(key="n")
    assert entry.expires_at is not None


async def test_increment_restarts_after_expiry(cache):
    await cache.set("n", 10, ttl=1)
    await asyncio.sleep(1.1)
    assert await cache.increment("n") == 1


async def test_prune_removes_only_expired(cache):
    await cache.set("old", 1, ttl=1)
    await cache.set("new", 1, ttl=60)
    await cache.forever("keep", 1)
    await asyncio.sleep(1.1)
    assert await DatabaseDriver().prune() == 1
    assert await CacheEntry.all().count() == 2


async def test_unregistered_model_gives_hint(monkeypatch):
    # a model missing from TORTOISE_ORM keeps default_connection = None
    monkeypatch.setattr(CacheEntry._meta, "default_connection", None)
    c = _Cache()
    c.configure(driver="database")
    with pytest.raises(ForgeAPIConfigError) as exc:
        await c.get("k")
    assert "forgeapi.cache.models" in (exc.value.hint or "")
