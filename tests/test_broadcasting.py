"""Tests for BroadcastManager, RedisDriver, and broadcast facade."""
import asyncio
import json
import logging
import uuid
from datetime import date, datetime
from decimal import Decimal

import pytest

import forgeapi.broadcasting.facade as _facade_mod
from forgeapi.broadcasting import BroadcastManager
from forgeapi.broadcasting.drivers.redis import RedisDriver, _json_default, _serialize
from forgeapi.broadcasting.facade import broadcast, configure, get


@pytest.fixture(autouse=True)
def reset_broadcast_facade():
    """Isolate the global broadcast instance between tests."""
    prev = _facade_mod._instance
    _facade_mod._instance = None
    yield
    _facade_mod._instance = prev


# ---------------------------------------------------------------------------
# Fake Redis helpers
# ---------------------------------------------------------------------------

class FakeRedis:
    def __init__(self):
        self.published: list[tuple] = []
        self.xadded: list[tuple] = []
        self.xacked: list[tuple] = []
        self.groups_created: list[tuple] = []
        self._xread_messages: list = []
        self._call_count = 0

    async def publish(self, channel, payload):
        self.published.append((channel, payload))

    def pubsub(self):
        return FakePubSub()

    async def xadd(self, key, fields, maxlen=None, approximate=None, **kwargs):
        self.xadded.append((key, dict(fields)))
        return b"1-0"

    async def xgroup_create(self, key, group, id="$", mkstream=False):
        self.groups_created.append((key, group, id))

    async def xreadgroup(self, groupname, consumername, streams, count=None, block=None):
        self._call_count += 1
        if self._xread_messages:
            return [self._xread_messages.pop(0)]
        await asyncio.sleep(9999)
        return []

    async def xack(self, key, group, msg_id):
        self.xacked.append((key, group, msg_id))

    async def aclose(self):
        pass


class FakePubSub:
    def __init__(self):
        self._messages: list = []

    async def psubscribe(self, pattern):
        pass

    async def punsubscribe(self, *_):
        pass

    async def aclose(self):
        pass

    async def get_message(self, ignore_subscribe_messages=True, timeout=1.0):
        if self._messages:
            return self._messages.pop(0)
        await asyncio.sleep(timeout)
        return None


def _make_stream_entry(channel: str, namespace: str, data: dict) -> tuple:
    key = f"{namespace}:{channel}".encode()
    fields = {k.encode(): json.dumps(v).encode() for k, v in data.items()}
    return (key, [(b"1-0", fields)])


# ---------------------------------------------------------------------------
# _json_default
# ---------------------------------------------------------------------------

class TestJsonDefault:
    def test_datetime(self):
        val = datetime(2024, 1, 15, 12, 0, 0)
        assert _json_default(val) == val.isoformat()

    def test_date(self):
        val = date(2024, 1, 15)
        assert _json_default(val) == val.isoformat()

    def test_decimal(self):
        val = Decimal("3.14")
        assert _json_default(val) == float(val)

    def test_uuid(self):
        val = uuid.UUID("12345678-1234-5678-1234-567812345678")
        assert _json_default(val) == str(val)

    def test_str_fallback(self):
        class Custom:
            def __str__(self):
                return "custom_str"
        assert _json_default(Custom()) == "custom_str"


# ---------------------------------------------------------------------------
# _serialize
# ---------------------------------------------------------------------------

class TestSerialize:
    def test_dict_passthrough(self):
        d = {"a": 1, "b": 2}
        assert _serialize(d) is d

    def test_plain_object(self):
        class Obj:
            def __init__(self):
                self.x = 10
                self.y = 20
                self._private = "hidden"
        result = _serialize(Obj())
        assert result == {"x": 10, "y": 20}


# ---------------------------------------------------------------------------
# BroadcastManager — construction
# ---------------------------------------------------------------------------

class TestBroadcastManagerInit:
    def test_default_driver_is_redis(self):
        bm = BroadcastManager()
        assert isinstance(bm._driver, RedisDriver)

    def test_unknown_driver_raises(self):
        with pytest.raises(ValueError, match="Unknown driver"):
            BroadcastManager(driver="rabbitmq")

    def test_pubsub_mode_stored(self):
        bm = BroadcastManager(mode="pubsub")
        assert bm._mode == "pubsub"

    def test_stream_mode_stored(self):
        bm = BroadcastManager(mode="stream")
        assert bm._mode == "stream"


# ---------------------------------------------------------------------------
# BroadcastManager.on() — handler registration
# ---------------------------------------------------------------------------

class TestOnDecorator:
    def test_registers_handler(self):
        bm = BroadcastManager()

        @bm.on("order:created")
        async def handler(data: dict): pass

        assert "order:created" in bm._driver._handlers
        assert handler in bm._driver._handlers["order:created"]

    def test_multiple_handlers_same_channel(self):
        bm = BroadcastManager()

        @bm.on("ping")
        async def h1(data: dict): pass

        @bm.on("ping")
        async def h2(data: dict): pass

        assert len(bm._driver._handlers["ping"]) == 2

    def test_returns_original_function(self):
        bm = BroadcastManager()

        @bm.on("x")
        async def handler(data: dict): pass

        assert callable(handler)


# ---------------------------------------------------------------------------
# BroadcastManager.emit() — pubsub
# ---------------------------------------------------------------------------

class TestEmitPubsub:
    @pytest.mark.anyio
    async def test_emit_before_connect_raises(self):
        bm = BroadcastManager(mode="pubsub")
        with pytest.raises(RuntimeError, match="not connected"):
            await bm.emit("test", {"x": 1})

    @pytest.mark.anyio
    async def test_emit_publishes_json(self):
        bm = BroadcastManager(namespace="shop", mode="pubsub")
        fake = FakeRedis()
        bm._driver._redis = fake

        await bm.emit("order:created", {"id": 42})

        assert len(fake.published) == 1
        channel, payload = fake.published[0]
        assert channel == "shop:order:created"
        assert json.loads(payload) == {"id": 42}

    @pytest.mark.anyio
    async def test_emit_uses_namespace(self):
        bm = BroadcastManager(namespace="myapp", mode="pubsub")
        fake = FakeRedis()
        bm._driver._redis = fake

        await bm.emit("sale:started", {})
        channel, _ = fake.published[0]
        assert channel == "myapp:sale:started"


# ---------------------------------------------------------------------------
# BroadcastManager.emit() — stream
# ---------------------------------------------------------------------------

class TestEmitStream:
    @pytest.mark.anyio
    async def test_emit_xadd_with_correct_key(self):
        bm = BroadcastManager(namespace="shop", mode="stream", maxlen=500)
        fake = FakeRedis()
        bm._driver._redis = fake

        await bm.emit("order:created", {"id": 99})

        assert len(fake.xadded) == 1
        key, fields = fake.xadded[0]
        assert key == "shop:order:created"
        assert json.loads(fields["id"]) == 99

    @pytest.mark.anyio
    async def test_emit_stream_fields_are_json_strings(self):
        bm = BroadcastManager(namespace="ns", mode="stream")
        fake = FakeRedis()
        bm._driver._redis = fake

        await bm.emit("ev", {"x": 1, "y": "hello"})

        _, fields = fake.xadded[0]
        for v in fields.values():
            json.loads(v)  # must not raise


# ---------------------------------------------------------------------------
# BroadcastManager.connect() — validation
# ---------------------------------------------------------------------------

class TestConnect:
    @pytest.mark.anyio
    async def test_stream_connect_requires_group_and_consumer(self):
        bm = BroadcastManager(mode="stream")
        bm._driver._redis = FakeRedis()

        @bm.on("ch")
        async def h(data): pass

        with pytest.raises(ValueError, match="group and consumer"):
            await bm.connect()

    @pytest.mark.anyio
    async def test_stream_connect_no_handlers_is_emit_only(self):
        bm = BroadcastManager(mode="stream")
        bm._driver._redis = FakeRedis()

        # no handlers → emit-only mode, connect() returns without starting listener
        await bm.connect(group="g", consumer="c")
        assert bm._listen_task is None

    @pytest.mark.anyio
    async def test_connect_creates_listen_task(self):
        bm = BroadcastManager(namespace="ns", mode="stream")
        fake = FakeRedis()
        bm._driver._redis = fake

        @bm.on("ch")
        async def h(data): pass

        await bm.connect(group="g", consumer="c")
        assert bm._listen_task is not None
        assert not bm._listen_task.done()
        await bm.disconnect()

    @pytest.mark.anyio
    async def test_disconnect_cancels_task(self):
        bm = BroadcastManager(namespace="ns", mode="stream")
        fake = FakeRedis()
        bm._driver._redis = fake

        @bm.on("ch")
        async def h(data): pass

        await bm.connect(group="g", consumer="c")
        task = bm._listen_task
        await bm.disconnect()
        assert task.done()
        assert bm._listen_task is None


# ---------------------------------------------------------------------------
# RedisDriver — stream consumer group creation
# ---------------------------------------------------------------------------

class TestStreamGroupCreation:
    @pytest.mark.anyio
    async def test_creates_group_on_connect(self):
        bm = BroadcastManager(namespace="ns", mode="stream")
        fake = FakeRedis()
        bm._driver._redis = fake

        @bm.on("orders")
        async def h(data): pass

        await bm.connect(group="backend", consumer="w1")
        await asyncio.sleep(0)
        await bm.disconnect()

        assert any(
            key == "ns:orders" and group == "backend"
            for key, group, _ in fake.groups_created
        )

    @pytest.mark.anyio
    async def test_busygroup_does_not_crash(self):
        bm = BroadcastManager(namespace="ns", mode="stream")

        class BusyRedis(FakeRedis):
            async def xgroup_create(self, *args, **kwargs):
                raise Exception("BUSYGROUP Consumer Group name already exists")

        bm._driver._redis = BusyRedis()

        @bm.on("orders")
        async def h(data): pass

        await bm.connect(group="g", consumer="c")
        await asyncio.sleep(0)
        await bm.disconnect()


# ---------------------------------------------------------------------------
# RedisDriver — stream message dispatch
# ---------------------------------------------------------------------------

class TestStreamDispatch:
    @pytest.mark.anyio
    async def test_message_delivered_to_handler(self):
        bm = BroadcastManager(namespace="ns", mode="stream")
        received = []

        @bm.on("orders")
        async def handler(data: dict):
            received.append(data["id"])

        fake = FakeRedis()
        fake._xread_messages = [_make_stream_entry("orders", "ns", {"id": 42})]
        bm._driver._redis = fake

        await bm.connect(group="g", consumer="c")
        await asyncio.sleep(0.1)
        await bm.disconnect()

        assert received == [42]

    @pytest.mark.anyio
    async def test_xack_called_after_processing(self):
        bm = BroadcastManager(namespace="ns", mode="stream")

        @bm.on("orders")
        async def handler(data: dict): pass

        fake = FakeRedis()
        fake._xread_messages = [_make_stream_entry("orders", "ns", {"id": 1})]
        bm._driver._redis = fake

        await bm.connect(group="g", consumer="c")
        await asyncio.sleep(0.1)
        await bm.disconnect()

        assert len(fake.xacked) == 1
        key, group, _ = fake.xacked[0]
        assert key == "ns:orders"
        assert group == "g"

    @pytest.mark.anyio
    async def test_xack_called_even_if_handler_raises(self):
        bm = BroadcastManager(namespace="ns", mode="stream")

        @bm.on("orders")
        async def handler(data: dict):
            raise RuntimeError("handler crash")

        fake = FakeRedis()
        fake._xread_messages = [_make_stream_entry("orders", "ns", {"id": 1})]
        bm._driver._redis = fake

        await bm.connect(group="g", consumer="c")
        await asyncio.sleep(0.1)
        await bm.disconnect()

        assert len(fake.xacked) == 1


# ---------------------------------------------------------------------------
# RedisDriver — pubsub dispatch
# ---------------------------------------------------------------------------

class TestPubsubDispatch:
    @pytest.mark.anyio
    async def test_dispatch_pubsub_routes_to_handler(self):
        driver = RedisDriver(url="redis://localhost", namespace="ns", mode="pubsub", maxlen=None)
        received = []

        async def handler(data: dict):
            received.append(data)

        driver.register("ping", handler)

        message = {
            "type": "pmessage",
            "channel": "ns:ping",
            "data": json.dumps({"msg": "hello"}),
        }
        await driver._dispatch_pubsub(message)
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        assert received == [{"msg": "hello"}]

    @pytest.mark.anyio
    async def test_dispatch_pubsub_unknown_channel_is_noop(self):
        driver = RedisDriver(url="redis://localhost", namespace="ns", mode="pubsub", maxlen=None)
        message = {"type": "pmessage", "channel": "ns:unknown", "data": "{}"}
        await driver._dispatch_pubsub(message)  # must not raise

    @pytest.mark.anyio
    async def test_dispatch_pubsub_invalid_json_logs_error(self, caplog):
        driver = RedisDriver(url="redis://localhost", namespace="ns", mode="pubsub", maxlen=None)

        async def handler(data: dict): pass
        driver.register("x", handler)

        message = {"type": "pmessage", "channel": "ns:x", "data": "not json {{{"}
        with caplog.at_level(logging.ERROR, logger="forgeapi.broadcasting.redis"):
            await driver._dispatch_pubsub(message)

        assert any("failed to parse" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# RedisDriver._safe_call
# ---------------------------------------------------------------------------

class TestSafeCall:
    @pytest.mark.anyio
    async def test_suppresses_exception_and_logs(self, caplog):
        driver = RedisDriver(url="redis://localhost", namespace="ns", mode="pubsub", maxlen=None)

        async def bad(data):
            raise ValueError("handler error")

        with caplog.at_level(logging.ERROR, logger="forgeapi.broadcasting.redis"):
            await driver._safe_call(bad, {})

        assert any("handler error" in r.message for r in caplog.records)

    @pytest.mark.anyio
    async def test_does_not_raise(self):
        driver = RedisDriver(url="redis://localhost", namespace="ns", mode="pubsub", maxlen=None)

        async def bad(data):
            raise RuntimeError("boom")

        await driver._safe_call(bad, {})  # must not raise


# ---------------------------------------------------------------------------
# broadcast facade
# ---------------------------------------------------------------------------

class TestBroadcastFacade:
    def test_get_raises_when_not_configured(self):
        with pytest.raises(RuntimeError, match="not configured"):
            get()

    def test_configure_returns_broadcast_manager(self):
        bm = configure(namespace="test")
        assert isinstance(bm, BroadcastManager)

    def test_configure_stores_instance(self):
        configure(namespace="test")
        assert _facade_mod._instance is not None

    def test_get_returns_configured_instance(self):
        bm = configure(namespace="test")
        assert get() is bm

    def test_configure_twice_replaces_instance(self):
        bm1 = configure(namespace="a")
        bm2 = configure(namespace="b")
        assert get() is bm2
        assert bm1 is not bm2

    def test_proxy_is_configured_false_by_default(self):
        assert broadcast.is_configured is False

    def test_proxy_is_configured_true_after_configure(self):
        configure(namespace="test")
        assert broadcast.is_configured is True

    def test_proxy_on_raises_when_not_configured(self):
        with pytest.raises(RuntimeError, match="not configured"):
            broadcast.on("test")

    def test_proxy_on_registers_handler_when_configured(self):
        bm = configure(namespace="test")

        @broadcast.on("order:created")
        async def handler(data: dict): pass

        assert "order:created" in bm._driver._handlers
        assert handler in bm._driver._handlers["order:created"]

    @pytest.mark.anyio
    async def test_proxy_emit_raises_when_not_configured(self):
        with pytest.raises(RuntimeError, match="not configured"):
            await broadcast.emit("test", {})

    @pytest.mark.anyio
    async def test_proxy_emit_delegates_to_manager(self):
        bm = configure(namespace="shop", mode="pubsub")
        fake = FakeRedis()
        bm._driver._redis = fake

        await broadcast.emit("order:created", {"id": 1})

        assert len(fake.published) == 1
        channel, _ = fake.published[0]
        assert channel == "shop:order:created"
