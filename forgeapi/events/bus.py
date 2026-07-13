import asyncio
import contextlib
import hashlib
import importlib.util
import json
import logging
import sys
import threading
from pathlib import Path
from typing import Any, Awaitable, Callable, ClassVar, Type, TypeVar

from .event import Event

logger = logging.getLogger("forgeapi.events")

E = TypeVar("E", bound=Event)

_CHANNEL_PREFIX = "forgeapi:events:"
_DEDUP_PREFIX = "forgeapi:events:dedup:"


class EventBus:
    """Central event dispatcher — singleton registry of event → listeners.

    You rarely need to interact with ``EventBus`` directly.  Use the
    :func:`~forgeapi.events.decorators.listen` decorator or
    :meth:`on` to register listeners, and
    :meth:`~forgeapi.events.event.Event.dispatch` to fire events.

    The singleton is created on first access via :meth:`get_instance`.  Call
    :meth:`reset` between test cases to start with an empty registry.

    Redis pub/sub
    -------------
    Call :meth:`set_redis` with an ``redis.asyncio`` client to enable the
    Redis transport.  Events with ``redis = True`` are then published to a
    Redis channel instead of being dispatched locally.  Run
    :meth:`start_redis_subscriber` as a background task to receive those
    events and dispatch them to local listeners::

        redis_client = redis.asyncio.from_url("redis://localhost:6379")
        bus = EventBus.get_instance()
        bus.set_redis(redis_client)

        async with asyncio.TaskGroup() as tg:
            tg.create_task(bus.start_redis_subscriber())

    Example — manual registration (without the decorator)::

        bus = EventBus.get_instance()
        bus.register(OrderCreated, my_async_handler)

    Example — instance-based decorator::

        bus = EventBus.get_instance()

        @bus.on(OrderCreated)
        async def handle_order(event: OrderCreated) -> None:
            ...

    Example — loading all listeners from a directory::

        bus = EventBus.get_instance()
        bus.load_from_dir("app/listeners")
    """

    _instance: "EventBus | None" = None
    _lock: ClassVar[threading.Lock] = threading.Lock()

    def __init__(self) -> None:
        self._listeners: dict[type, list[Callable]] = {}
        self._redis: Any = None
        self._bg_tasks: set[asyncio.Task] = set()
        self._subscriber_task: asyncio.Task | None = None

    # ------------------------------------------------------------------
    # Singleton
    # ------------------------------------------------------------------

    @classmethod
    def get_instance(cls) -> "EventBus":
        """Return the process-wide singleton instance."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Destroy the singleton and clear all registered listeners.

        Intended for use in tests so each test case starts with a clean slate::

            @pytest.fixture(autouse=True)
            def reset_event_bus():
                EventBus.reset()
                yield
                EventBus.reset()

        Note: ``reset()`` schedules task cancellation but cannot await it.  In
        production code (e.g. application shutdown) prefer
        :meth:`drain` before calling ``reset()``, or cancel the subscriber task
        explicitly and await it before calling ``reset()``.
        """
        if cls._instance is not None:
            task = getattr(cls._instance, "_subscriber_task", None)
            if task and not task.done():
                task.cancel()
        cls._instance = None

    # ------------------------------------------------------------------
    # Redis
    # ------------------------------------------------------------------

    def set_redis(self, client: Any) -> None:
        """Attach a ``redis.asyncio`` client for pub/sub transport.

        Once set, any :class:`~forgeapi.events.event.Event` with
        ``redis = True`` will be published to a Redis channel on dispatch
        instead of being run locally.  Local listeners are invoked by the
        subscriber worker started with :meth:`start_redis_subscriber`.

        Args:
            client: An ``redis.asyncio`` client (or compatible interface).

        Example::

            import redis.asyncio as aioredis
            from forgeapi import EventBus

            bus = EventBus.get_instance()
            bus.set_redis(aioredis.from_url("redis://localhost:6379"))
        """
        self._redis = client

    async def redis_connect(self, url: str) -> None:
        """Create a Redis client from *url* and attach it to this bus.

        Prefer this over :meth:`set_redis` when you don't need a manually
        created client — no ``redis.asyncio`` import required in your code::

            bus = EventBus.get_instance()
            await bus.redis_connect("redis://localhost:6379")
            # ...
            await bus.redis_disconnect()

        Args:
            url: Redis connection URL, e.g. ``"redis://localhost:6379"``.

        Raises:
            ImportError: If the ``redis`` package is not installed.
        """
        try:
            import redis.asyncio as aioredis
        except ImportError:
            raise ImportError(
                "EventBus.redis_connect() requires the redis package. "
                "Install it: pip install redis"
            )
        self._redis = aioredis.from_url(url, decode_responses=False)

    async def redis_disconnect(self) -> None:
        """Close the Redis connection created by :meth:`redis_connect`.

        Safe to call even if Redis was attached via :meth:`set_redis` or
        if the bus has no Redis client at all.
        """
        if self._redis is not None:
            with contextlib.suppress(Exception):
                await self._redis.aclose()
            self._redis = None

    async def start_redis_subscriber(self) -> None:
        """Subscribe to all event channels and dispatch incoming events locally.

        This coroutine runs indefinitely and should be started as a background
        task in the application lifespan::

            task = asyncio.create_task(bus.start_redis_subscriber())
            # on shutdown:
            task.cancel()

        For each received message:

        1. Deserialise the event via :meth:`~forgeapi.events.event.Event.from_dict`.
        2. If ``event.ttl`` is set, attempt to acquire a Redis dedup lock
           (``SET NX EX``).  If another worker already holds it, skip.
        3. Dispatch to local listeners (honouring ``event.background``).

        Raises:
            RuntimeError: If Redis has not been configured via :meth:`set_redis`.
        """
        if self._redis is None:
            raise RuntimeError(
                "Redis client not configured. Call EventBus.set_redis() first."
            )

        retry_delay = 1.0
        try:
            while True:
                pubsub = None
                try:
                    pubsub = self._redis.pubsub()
                    await pubsub.psubscribe(f"{_CHANNEL_PREFIX}*")
                    logger.debug(
                        "Redis subscriber started, listening on '%s*'", _CHANNEL_PREFIX
                    )
                    retry_delay = 1.0
                    while True:
                        message = await pubsub.get_message(
                            ignore_subscribe_messages=True,
                            timeout=1.0,
                        )
                        if message is not None and message.get("type") == "pmessage":
                            await self._handle_redis_message(message["data"])
                except asyncio.CancelledError:
                    break
                except Exception as exc:
                    logger.error(
                        "Redis subscriber error, reconnecting in %.1fs: %s",
                        retry_delay,
                        exc,
                    )
                    await asyncio.sleep(retry_delay)
                    retry_delay = min(retry_delay * 2, 60.0)
                finally:
                    if pubsub is not None:
                        with contextlib.suppress(Exception):
                            await pubsub.punsubscribe(f"{_CHANNEL_PREFIX}*")
                        with contextlib.suppress(Exception):
                            await pubsub.aclose()
        finally:
            logger.debug("Redis subscriber stopped")

    async def _handle_redis_message(self, raw: bytes | str) -> None:
        try:
            data = json.loads(raw)
            event = Event.from_dict(data)
        except Exception as exc:
            logger.error("Failed to deserialise Redis event: %s", exc, exc_info=exc)
            return

        if event.ttl is not None:
            acquired = await self._dedup_check(event.event_id, event.ttl)
            if not acquired:
                logger.debug(
                    "Event '%s' (id=%s) already processed, skipping",
                    type(event).__name__,
                    event.event_id,
                )
                return

        listeners = self.listeners_for(type(event))
        if not listeners:
            return

        if event.background:
            t = asyncio.create_task(
                self._run_all(event, listeners),
                name=f"event:{type(event).__name__}",
            )
            self._bg_tasks.add(t)
            t.add_done_callback(self._bg_tasks.discard)
        else:
            await self._run_all(event, listeners)

    async def _dedup_check(self, event_id: str, ttl: int) -> bool:
        """Try to acquire the dedup lock for *event_id*.

        Uses Redis ``SET NX EX`` — only the first worker to call this for a
        given ``event_id`` returns ``True``; subsequent callers return
        ``False`` until the key expires.

        Args:
            event_id: Unique identifier of the event instance.
            ttl: Lock expiry in seconds.

        Returns:
            ``True`` if this worker should process the event.
        """
        key = f"{_DEDUP_PREFIX}{event_id}"
        try:
            result = await self._redis.set(key, "1", nx=True, ex=ttl)
            return result is not None
        except Exception as exc:
            logger.error(
                "Redis dedup check failed for event_id=%s: %s", event_id, exc, exc_info=exc
            )
            return True  # allow processing when dedup is unavailable

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, event_class: type, listener: Callable) -> None:
        """Register *listener* to be called when *event_class* is dispatched.

        Args:
            event_class: The :class:`~forgeapi.events.event.Event` subclass
                to listen for.
            listener: An ``async def`` function that accepts a single argument
                of type *event_class*.

        Raises:
            TypeError: If *listener* is not a coroutine function (``async def``).
        """
        if not asyncio.iscoroutinefunction(listener):
            raise TypeError(
                f"Listener {listener!r} must be an async function (async def). "
                "Synchronous callables are not supported."
            )
        bucket = self._listeners.setdefault(event_class, [])
        if listener not in bucket:
            bucket.append(listener)
        else:
            logger.warning(
                "Listener %r already registered for %s, skipping duplicate",
                listener,
                event_class.__name__,
            )

    def on(
        self,
        event_class: Type[E],
    ) -> Callable[[Callable[[E], Awaitable[None]]], Callable[[E], Awaitable[None]]]:
        """Register an async function as a listener via decorator syntax.

        Instance-based alternative to :func:`~forgeapi.events.decorators.listen`.
        Both register on the same singleton; the difference is purely stylistic.

        Args:
            event_class: The :class:`~forgeapi.events.event.Event` subclass
                to subscribe to.

        Example::

            bus = EventBus.get_instance()

            @bus.on(OrderShipped)
            async def notify_warehouse(event: OrderShipped) -> None:
                await warehouse_api.notify(event.order_id)

            @bus.on(OrderShipped)
            async def update_analytics(event: OrderShipped) -> None:
                await analytics.track("order_shipped", order_id=event.order_id)
        """
        def decorator(
            func: Callable[[E], Awaitable[None]],
        ) -> Callable[[E], Awaitable[None]]:
            self.register(event_class, func)
            return func

        return decorator

    def listeners_for(self, event_class: type) -> list[Callable]:
        """Return all listeners registered for *event_class*."""
        return self._listeners.get(event_class, [])

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------

    async def _publish_stream(self, event: Event) -> None:
        """Publish *event* to a Redis Stream via XADD."""
        namespace = getattr(type(event), "namespace", "forgeapi:events")
        stream_key = f"{namespace}:{type(event).__name__}"
        fields = {k: json.dumps(v) for k, v in event.to_dict().items()}
        try:
            await self._redis.xadd(stream_key, fields, maxlen=10_000)
            logger.debug("Stream XADD '%s' id=%s", stream_key, event.event_id)
        except Exception as exc:
            logger.error("Failed to XADD event '%s': %s", type(event).__name__, exc, exc_info=exc)
            listeners = self.listeners_for(type(event))
            if listeners:
                await self._run_all(event, listeners)

    async def start_stream_subscriber(
        self,
        group: str,
        consumer: str,
        event_classes: list[type],
    ) -> None:
        """Consume events from Redis Streams using consumer groups.

        Each consumer group receives every message independently — two groups
        on the same stream both get all events (unlike pub/sub, messages are
        persisted until all groups ACK them).

        Args:
            group:         Consumer group name, e.g. ``"bot1"``.
            consumer:      Consumer instance name, e.g. ``"bot1-worker-1"``.
            event_classes: Event subclasses to subscribe to.  Their
                           ``namespace`` and class name determine the stream key.

        Example::

            task = asyncio.create_task(
                bus.start_stream_subscriber(
                    group="bot1",
                    consumer="bot1-1",
                    event_classes=[OrderEvent],
                )
            )
        """
        if self._redis is None:
            raise RuntimeError("Redis client not configured. Call EventBus.set_redis() first.")

        stream_keys: list[str] = []
        for cls in event_classes:
            namespace = getattr(cls, "namespace", "forgeapi:events")
            key = f"{namespace}:{cls.__name__}"
            stream_keys.append(key)
            try:
                await self._redis.xgroup_create(key, group, id="$", mkstream=True)
                logger.debug("Stream group '%s' created on '%s'", group, key)
            except Exception as exc:
                if "BUSYGROUP" in str(exc):
                    logger.debug("Stream group '%s' already exists on '%s'", group, key)
                else:
                    logger.error("xgroup_create failed for '%s': %s", key, exc)

        streams = {key: ">" for key in stream_keys}
        logger.debug("Stream subscriber started (group=%s consumer=%s keys=%s)", group, consumer, stream_keys)

        try:
            while True:
                try:
                    results = await self._redis.xreadgroup(
                        groupname=group,
                        consumername=consumer,
                        streams=streams,
                        count=10,
                        block=2000,
                    )
                    if not results:
                        continue
                    for stream_name, messages in results:
                        key = stream_name.decode() if isinstance(stream_name, bytes) else stream_name
                        for msg_id, raw_fields in messages:
                            await self._handle_stream_message(key, msg_id, raw_fields, group)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    logger.error("Stream subscriber error, retrying in 1s: %s", exc)
                    await asyncio.sleep(1)
        except asyncio.CancelledError:
            logger.debug("Stream subscriber stopped (group=%s consumer=%s)", group, consumer)

    async def _handle_stream_message(
        self,
        stream_key: str,
        msg_id: Any,
        raw_fields: dict,
        group: str,
    ) -> None:
        try:
            data: dict[str, Any] = {}
            for k, v in raw_fields.items():
                key = k.decode() if isinstance(k, bytes) else k
                val = v.decode() if isinstance(v, bytes) else v
                try:
                    data[key] = json.loads(val)
                except (json.JSONDecodeError, ValueError):
                    data[key] = val
            event = Event.from_dict(data)
        except Exception as exc:
            logger.error("Failed to deserialise stream message on '%s': %s", stream_key, exc, exc_info=exc)
            await self._redis.xack(stream_key, group, msg_id)
            return

        listeners = self.listeners_for(type(event))
        if listeners:
            if event.background:
                t = asyncio.create_task(
                    self._run_all(event, listeners),
                    name=f"event:{type(event).__name__}",
                )
                self._bg_tasks.add(t)
                t.add_done_callback(self._bg_tasks.discard)
            else:
                await self._run_all(event, listeners)

        await self._redis.xack(stream_key, group, msg_id)
        logger.debug("Stream XACK '%s' group=%s id=%s", stream_key, group, msg_id)

    async def dispatch(self, event: Event) -> None:
        """Fire *event* and invoke all registered listeners.

        If ``event.redis = True`` and a Redis client is configured:

        * ``event.redis_type = "stream"`` — publishes via ``XADD`` to
          ``{event.namespace}:{EventClassName}``.  Consumed by
          :meth:`start_stream_subscriber` worker(s).
        * ``event.redis_type = "pubsub"`` (default) — publishes via
          ``PUBLISH`` to ``forgeapi:events:{EventClassName}``.  Consumed by
          :meth:`start_redis_subscriber` worker.

        Otherwise (no Redis or ``event.redis = False``) the existing local
        dispatch path is used:

        * ``background = False`` (default): awaits ``asyncio.gather``.
        * ``background = True``: wraps in ``asyncio.create_task``.

        Args:
            event: An :class:`~forgeapi.events.event.Event` instance.
        """
        if self._redis is not None and event.redis:
            if getattr(type(event), "redis_type", "pubsub") == "stream":
                await self._publish_stream(event)
                return

            channel = f"{_CHANNEL_PREFIX}{type(event).__name__}"
            payload = json.dumps(event.to_dict())
            try:
                await self._redis.publish(channel, payload)
                return
            except Exception as exc:
                logger.error(
                    "Failed to publish event %s to Redis: %s",
                    type(event).__name__,
                    exc,
                    exc_info=exc,
                )
                # fallback: deliver locally

        listeners = self.listeners_for(type(event))
        if not listeners:
            return

        if event.background:
            t = asyncio.create_task(
                self._run_all(event, listeners),
                name=f"event:{type(event).__name__}",
            )
            self._bg_tasks.add(t)
            t.add_done_callback(self._bg_tasks.discard)
        else:
            await self._run_all(event, listeners)

    async def _run_all(self, event: Event, listeners: list[Callable]) -> None:
        results = await asyncio.gather(
            *(listener(event) for listener in listeners),
            return_exceptions=True,
        )
        for listener, result in zip(listeners, results):
            if isinstance(result, asyncio.CancelledError):
                raise result  # propagate cancellation instead of swallowing it
            if isinstance(result, BaseException):
                logger.error(
                    "Listener '%s' failed for event '%s': %s",
                    listener.__name__,
                    type(event).__name__,
                    result,
                    exc_info=result,
                )

    async def drain(self, timeout: float = 30.0) -> None:
        """Await all pending background tasks up to *timeout* seconds.

        Call this during application shutdown before :meth:`reset` to ensure
        in-flight fire-and-forget tasks complete cleanly.

        Args:
            timeout: Maximum seconds to wait for tasks to complete.
        """
        if self._bg_tasks:
            await asyncio.wait(self._bg_tasks, timeout=timeout)

    # ------------------------------------------------------------------
    # Auto-loading
    # ------------------------------------------------------------------

    def load_from_dir(self, directory: str) -> None:
        """Import all ``*.py`` files from *directory* to auto-register listeners.

        Each file is imported as an isolated module.  Any ``@listen(...)`` or
        ``@bus.on(...)`` decorators at module level execute on import and
        register their functions with this bus.  Files starting with ``_`` are
        skipped.  Already-imported files (by path) are skipped on subsequent
        calls.

        Args:
            directory: Relative or absolute path to the listeners directory
                (e.g. ``"app/listeners"``).
        """
        dir_path = Path(directory)
        if not dir_path.exists():
            logger.warning("Listeners directory not found: '%s'", directory)
            return

        for py_file in sorted(dir_path.glob("*.py")):
            if py_file.name.startswith("_"):
                continue
            self._import_file(py_file)

    def _import_file(self, path: Path) -> None:
        module_name = f"_fk_listener_{hashlib.md5(str(path.resolve()).encode(), usedforsecurity=False).hexdigest()}"
        if module_name in sys.modules:
            return

        spec = importlib.util.spec_from_file_location(module_name, path)
        if not spec or not spec.loader:
            logger.warning("Cannot load listener file: %s", path)
            return

        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        try:
            spec.loader.exec_module(module)
            logger.debug("Loaded listeners from '%s'", path)
        except Exception as exc:
            del sys.modules[module_name]
            logger.error("Failed to load listener file '%s': %s", path, exc, exc_info=exc)
