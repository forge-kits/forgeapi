import asyncio
import json
import logging
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Awaitable, Callable

logger = logging.getLogger("forgeapi.events.redis_bus")

try:
    from tortoise.models import Model as _TortoiseModel
except ImportError:
    _TortoiseModel = None  # type: ignore[assignment,misc]


def _json_default(obj: Any) -> Any:
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, uuid.UUID):
        return str(obj)
    if hasattr(obj, "__str__"):
        return str(obj)
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def _serialize(data: Any) -> dict:
    if isinstance(data, dict):
        return data
    if hasattr(data, "_meta"):
        result = {}
        for k, v in data.__dict__.items():
            if k.startswith("_"):
                continue
            if _TortoiseModel is not None and isinstance(v, _TortoiseModel):
                continue
            result[k] = v
        return result
    return {k: v for k, v in vars(data).items() if not k.startswith("_")}


class RedisBus:
    """Standalone Redis pub/sub event bus for cross-project communication.

    Each project creates its own ``RedisBus`` instance connected to the same
    Redis server.  Events are published to named channels and received by any
    subscriber listening on the same namespace, regardless of which project or
    process published them.

    Args:
        url: Redis connection URL, e.g. ``"redis://localhost:6379"``.
        namespace: Prefix added to every channel to isolate projects from each
            other.  Defaults to ``"forge"``.  Use a unique value per project
            (e.g. ``"shop"``, ``"notifications"``) if the projects should NOT
            receive each other's events.

    Channels are named ``{namespace}:{channel}``, so with
    ``namespace="shop"`` and ``channel="order:created"`` the Redis channel is
    ``shop:order:created``.

    Project A (publisher)::

        bus = RedisBus("redis://localhost:6379", namespace="shop")

        # inside an async route / task
        order = await Order.get(id=42)
        await bus.emit("order:created", order)          # Tortoise model → dict
        await bus.emit("order:created", {"id": 42})     # plain dict also fine

    Project B (subscriber)::

        bus = RedisBus("redis://localhost:6379", namespace="shop")

        @bus.on("order:created")
        async def handle_order(data: dict) -> None:
            await telegram.send(f"New order #{data['id']}")
            await bus.emit("notification:sent", {"order_id": data["id"]})

        # FastAPI lifespan
        @asynccontextmanager
        async def lifespan(app):
            async with bus:
                yield

        # or standalone script
        async def main():
            async with bus:
                await asyncio.sleep(float("inf"))

        asyncio.run(main())

    Both projects can publish and subscribe simultaneously.  Handlers run as
    independent ``asyncio.Task`` objects so a slow handler does not block the
    listener loop.
    """

    def __init__(self, url: str, namespace: str = "forge") -> None:
        self._url = url
        self._namespace = namespace
        self._handlers: dict[str, list[Callable[[dict], Awaitable[None]]]] = {}
        self._redis: Any = None
        self._bg_tasks: set[asyncio.Task] = set()
        self._listener_task: asyncio.Task | None = None

    # ── Registration ──────────────────────────────────────────────────────────

    def on(
        self,
        channel: str,
    ) -> Callable[[Callable[[dict], Awaitable[None]]], Callable[[dict], Awaitable[None]]]:
        """Register an async handler for *channel*.

        Can be used as a decorator at module level — the handler is registered
        immediately and is active once :meth:`listen` is running.

        Args:
            channel: Channel name without namespace prefix, e.g.
                ``"order:created"``.

        Example::

            @bus.on("order:created")
            async def handle(data: dict) -> None:
                print(data["id"])

            @bus.on("order:created")   # multiple handlers on same channel — all run
            async def log_order(data: dict) -> None:
                logger.info("order received: %s", data)
        """
        def decorator(
            func: Callable[[dict], Awaitable[None]],
        ) -> Callable[[dict], Awaitable[None]]:
            self._handlers.setdefault(channel, []).append(func)
            logger.debug("RedisBus: registered handler '%s' on '%s'", func.__name__, channel)
            return func
        return decorator

    # ── Publish ───────────────────────────────────────────────────────────────

    async def emit(self, channel: str, data: Any) -> None:
        """Publish *data* to *channel*.

        *data* may be:

        * a plain ``dict`` — used as-is.
        * a **Tortoise ORM model** instance — scalar fields are extracted
          automatically; un-fetched relations are skipped (only the ``_id``
          FK column is included).  Pre-fetch relations before calling
          ``emit`` if you need them in the payload.
        * any object with a ``__dict__`` — public attributes are serialised.

        Non-JSON-serialisable values (``datetime``, ``Decimal``, ``UUID``)
        are converted automatically.

        Args:
            channel: Channel name without namespace prefix.
            data: Payload to send.

        Raises:
            RuntimeError: If :meth:`connect` has not been called yet.

        Example::

            # plain dict
            await bus.emit("order:created", {"id": 42, "total": 99.9})

            # Tortoise model — scalar fields auto-serialised
            order = await Order.get(id=42)
            await bus.emit("order:created", order)

            # pre-fetched relation is included
            order = await Order.get(id=42).prefetch_related("items")
            await bus.emit("order:created", order)
        """
        if self._redis is None:
            raise RuntimeError(
                "RedisBus is not connected. "
                "Use 'async with bus:' or call 'await bus.connect()' first."
            )
        redis_channel = f"{self._namespace}:{channel}"
        payload = json.dumps(_serialize(data), default=_json_default)
        await self._redis.publish(redis_channel, payload)
        logger.debug("RedisBus: emitted to '%s'", redis_channel)

    # ── Listen ────────────────────────────────────────────────────────────────

    async def listen(self) -> None:
        """Subscribe to all channels in this namespace and dispatch messages.

        This coroutine runs indefinitely.  It is safe to run inside an
        existing ``asyncio`` event loop — it does **not** create a new one::

            # inside FastAPI lifespan (existing event loop)
            task = asyncio.create_task(bus.listen())
            # on shutdown:
            task.cancel()

        For standalone scripts use the context manager instead::

            async with bus:
                await asyncio.sleep(float("inf"))

        Raises:
            RuntimeError: If :meth:`connect` has not been called yet.
        """
        if self._redis is None:
            raise RuntimeError(
                "RedisBus is not connected. Call 'await bus.connect()' first."
            )

        pattern = f"{self._namespace}:*"
        pubsub = self._redis.pubsub()
        await pubsub.psubscribe(pattern)
        logger.debug("RedisBus: listening on pattern '%s'", pattern)

        try:
            async for message in pubsub.listen():
                if message["type"] != "pmessage":
                    continue
                await self._dispatch(message)
        except asyncio.CancelledError:
            pass
        finally:
            try:
                await pubsub.punsubscribe(pattern)
                await pubsub.aclose()
            except Exception as exc:
                logger.debug("RedisBus: error during pubsub cleanup: %s", exc)
            logger.debug("RedisBus: listener stopped")

    async def _dispatch(self, message: dict) -> None:
        raw_channel = message["channel"]
        if isinstance(raw_channel, bytes):
            raw_channel = raw_channel.decode()

        prefix = f"{self._namespace}:"
        channel = raw_channel.removeprefix(prefix)

        handlers = self._handlers.get(channel)
        if not handlers:
            return

        raw_data = message["data"]
        try:
            data = json.loads(raw_data)
        except (json.JSONDecodeError, TypeError):
            logger.error("RedisBus: failed to parse message on channel '%s'", channel)
            return

        for handler in handlers:
            t = asyncio.create_task(
                self._safe_call(handler, data),
                name=f"redis_bus:{channel}:{handler.__name__}",
            )
            self._bg_tasks.add(t)
            t.add_done_callback(self._bg_tasks.discard)

    async def _safe_call(self, handler: Callable, data: dict) -> None:
        try:
            await handler(data)
        except Exception as exc:
            logger.error(
                "RedisBus: handler '%s' raised: %s",
                handler.__name__,
                exc,
                exc_info=exc,
            )

    # ── Connection ────────────────────────────────────────────────────────────

    async def connect(self) -> None:
        """Open the Redis connection.

        Called automatically by the context manager.  Call manually only when
        you manage the lifecycle yourself.

        Raises:
            ImportError: If ``redis`` is not installed.
        """
        if self._redis is not None:
            return  # already connected
        try:
            import redis.asyncio as aioredis
        except ImportError:
            raise ImportError(
                "RedisBus requires the redis package. "
                "Install it: pip install redis"
            )
        self._redis = aioredis.from_url(self._url, decode_responses=True)
        logger.debug(
            "RedisBus: connected to '%s' (namespace='%s')",
            self._url,
            self._namespace,
        )

    async def disconnect(self) -> None:
        """Close the Redis connection."""
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None
            logger.debug("RedisBus: disconnected")

    # ── Context manager ───────────────────────────────────────────────────────

    async def __aenter__(self) -> "RedisBus":
        """Connect and start the listener task."""
        await self.connect()
        self._listener_task = asyncio.create_task(
            self.listen(),
            name="redis_bus:listener",
        )
        self._bg_tasks.add(self._listener_task)
        self._listener_task.add_done_callback(self._bg_tasks.discard)
        return self

    async def __aexit__(self, *_: Any) -> None:
        """Cancel the listener task and disconnect."""
        if self._listener_task and not self._listener_task.done():
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass
        self._listener_task = None
        await self.disconnect()
