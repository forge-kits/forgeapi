import asyncio
import pytest

from forgeapi.events.bus import EventBus
from forgeapi.events.event import Event
from forgeapi.events.decorators import listen


# ---------------------------------------------------------------------------
# Fixture event types
# ---------------------------------------------------------------------------

class OrderCreated(Event):
    def __init__(self, order_id: int) -> None:
        self.order_id = order_id


class UserRegistered(Event):
    background = True

    def __init__(self, user_id: int) -> None:
        self.user_id = user_id


class RedisEvent(Event):
    redis = True
    ttl = 60

    def __init__(self, value: str) -> None:
        self.value = value


# ---------------------------------------------------------------------------
# Event class
# ---------------------------------------------------------------------------

class TestEvent:
    def test_event_id_is_unique(self):
        e1 = OrderCreated(1)
        e2 = OrderCreated(2)
        assert e1.event_id != e2.event_id

    def test_event_id_is_string(self):
        e = OrderCreated(1)
        assert isinstance(e.event_id, str)

    def test_to_dict_includes_type_key(self):
        e = OrderCreated(10)
        d = e.to_dict()
        assert d["_event_type"] == "OrderCreated"
        assert d["order_id"] == 10

    def test_from_dict_restores_subclass(self):
        e = OrderCreated(99)
        d = e.to_dict()
        restored = Event.from_dict(d)
        assert isinstance(restored, OrderCreated)
        assert restored.order_id == 99

    def test_from_dict_preserves_event_id(self):
        e = OrderCreated(7)
        d = e.to_dict()
        restored = Event.from_dict(d)
        assert restored.event_id == e.event_id

    def test_registry_contains_subclass(self):
        assert "OrderCreated" in Event._registry
        assert Event._registry["OrderCreated"] is OrderCreated

    def test_from_dict_unknown_type_raises(self):
        with pytest.raises(KeyError):
            Event.from_dict({"_event_type": "NoSuchEvent_XYZ_1234"})

    def test_class_flags_defaults(self):
        class SimpleEvent(Event):
            pass
        assert SimpleEvent.background is False
        assert SimpleEvent.redis is False
        assert SimpleEvent.ttl is None

    def test_background_flag(self):
        assert UserRegistered.background is True

    def test_redis_flag(self):
        assert RedisEvent.redis is True
        assert RedisEvent.ttl == 60


# ---------------------------------------------------------------------------
# EventBus singleton
# ---------------------------------------------------------------------------

class TestEventBusSingleton:
    def test_get_instance_returns_same_object(self):
        bus1 = EventBus.get_instance()
        bus2 = EventBus.get_instance()
        assert bus1 is bus2

    def test_reset_clears_singleton(self):
        bus1 = EventBus.get_instance()
        EventBus.reset()
        bus2 = EventBus.get_instance()
        assert bus1 is not bus2

    def test_reset_clears_listeners(self):
        bus = EventBus.get_instance()

        async def handler(e):
            pass

        bus.register(OrderCreated, handler)
        assert bus.listeners_for(OrderCreated)

        EventBus.reset()
        assert not EventBus.get_instance().listeners_for(OrderCreated)


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

class TestRegistration:
    def test_register_and_retrieve(self):
        bus = EventBus.get_instance()

        async def handler(e):
            pass

        bus.register(OrderCreated, handler)
        assert handler in bus.listeners_for(OrderCreated)

    def test_multiple_listeners(self):
        bus = EventBus.get_instance()

        async def h1(e):
            pass

        async def h2(e):
            pass

        bus.register(OrderCreated, h1)
        bus.register(OrderCreated, h2)
        listeners = bus.listeners_for(OrderCreated)
        assert h1 in listeners
        assert h2 in listeners

    def test_listeners_for_unknown_event_is_empty(self):
        bus = EventBus.get_instance()
        assert bus.listeners_for(OrderCreated) == []

    def test_on_decorator(self):
        bus = EventBus.get_instance()

        @bus.on(OrderCreated)
        async def handler(e):
            pass

        assert handler in bus.listeners_for(OrderCreated)

    def test_on_decorator_returns_original_function(self):
        bus = EventBus.get_instance()

        @bus.on(OrderCreated)
        async def handler(e):
            pass

        assert callable(handler)

    def test_listen_decorator(self):
        @listen(OrderCreated)
        async def handler(e):
            pass

        bus = EventBus.get_instance()
        assert handler in bus.listeners_for(OrderCreated)


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

class TestDispatch:
    @pytest.mark.anyio
    async def test_dispatch_calls_listener(self):
        bus = EventBus.get_instance()
        received = []

        async def handler(e: OrderCreated):
            received.append(e.order_id)

        bus.register(OrderCreated, handler)
        await bus.dispatch(OrderCreated(42))
        assert received == [42]

    @pytest.mark.anyio
    async def test_dispatch_calls_multiple_listeners(self):
        bus = EventBus.get_instance()
        calls = []

        async def h1(e):
            calls.append("h1")

        async def h2(e):
            calls.append("h2")

        bus.register(OrderCreated, h1)
        bus.register(OrderCreated, h2)
        await bus.dispatch(OrderCreated(1))
        assert sorted(calls) == ["h1", "h2"]

    @pytest.mark.anyio
    async def test_dispatch_no_listeners_is_noop(self):
        bus = EventBus.get_instance()
        # Should not raise
        await bus.dispatch(OrderCreated(1))

    @pytest.mark.anyio
    async def test_dispatch_via_event_method(self):
        bus = EventBus.get_instance()
        received = []

        async def handler(e: OrderCreated):
            received.append(e.order_id)

        bus.register(OrderCreated, handler)
        await OrderCreated(99).dispatch()
        assert received == [99]

    @pytest.mark.anyio
    async def test_listener_exception_does_not_propagate(self):
        bus = EventBus.get_instance()
        calls = []

        async def bad(e):
            raise ValueError("listener failed")

        async def good(e):
            calls.append("good")

        bus.register(OrderCreated, bad)
        bus.register(OrderCreated, good)
        # Should not raise despite bad listener
        await bus.dispatch(OrderCreated(1))
        assert calls == ["good"]

    @pytest.mark.anyio
    async def test_background_dispatch_fires(self):
        bus = EventBus.get_instance()
        received = []

        async def handler(e: UserRegistered):
            received.append(e.user_id)

        bus.register(UserRegistered, handler)
        await UserRegistered(7).dispatch()
        # Multiple yields needed: create_task → gather → handler
        for _ in range(5):
            await asyncio.sleep(0)
        assert received == [7]

    @pytest.mark.anyio
    async def test_redis_dispatch_publishes_not_local(self):
        bus = EventBus.get_instance()
        received = []

        async def handler(e):
            received.append(True)

        bus.register(RedisEvent, handler)

        published = []

        class FakeRedis:
            async def publish(self, channel, payload):
                published.append((channel, payload))

        bus.set_redis(FakeRedis())
        await RedisEvent("hello").dispatch()

        assert len(published) == 1
        assert "forgeapi:events:RedisEvent" in published[0][0]
        # Local listener was NOT called directly
        assert received == []
