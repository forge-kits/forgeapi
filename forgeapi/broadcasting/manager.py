import asyncio
from typing import Any, Awaitable, Callable

from forgeapi.logging import log

_log = log.channel("broadcasting")

_DRIVERS = ("redis",)


class BroadcastManager:
    """Universal broadcast manager with pluggable transport drivers.

    Supports ``mode="pubsub"`` (fire-and-forget) and ``mode="stream"``
    (persistent, consumer groups) via the Redis driver.  RabbitMQ driver
    is planned for a future release.

    Args:
        driver:    Transport backend. Currently only ``"redis"``.
        url:       Connection URL, e.g. ``"redis://localhost:6379"``.
        namespace: Prefix for all channel/stream keys.
        mode:      ``"pubsub"`` or ``"stream"`` (stream mode only for Redis).
        maxlen:    Max messages to keep per stream key (stream mode only).

    Example::

        broadcast = BroadcastManager(
            driver="redis",
            url="redis://localhost:6379",
            namespace="shop",
            mode="stream",
            maxlen=1000,
        )

        @broadcast.on("order:created")
        async def handle(data: dict) -> None:
            print(data["id"])

        # FastAPI lifespan
        @asynccontextmanager
        async def lifespan(app):
            await broadcast.connect(group="backend", consumer="worker-1")
            yield
            await broadcast.disconnect()
    """

    def __init__(
        self,
        driver: str = "redis",
        url: str = "redis://localhost:6379",
        namespace: str = "forge",
        mode: str = "pubsub",
        maxlen: int | None = None,
    ) -> None:
        if driver not in _DRIVERS:
            raise ValueError(f"Unknown driver '{driver}'. Available: {_DRIVERS}")
        self._mode = mode
        self._driver = self._make_driver(driver, url, namespace, mode, maxlen)
        self._listen_task: asyncio.Task | None = None

    def _make_driver(self, driver: str, url: str, namespace: str, mode: str, maxlen: int | None):
        if driver == "redis":
            from .drivers.redis import RedisDriver
            return RedisDriver(url=url, namespace=namespace, mode=mode, maxlen=maxlen)
        raise ValueError(f"Unknown driver: {driver}")

    # ── Registration ──────────────────────────────────────────────────────────

    def on(
        self,
        channel: str,
    ) -> Callable[[Callable[[dict], Awaitable[None]]], Callable[[dict], Awaitable[None]]]:
        """Register an async handler for *channel*.

        Use as a decorator at module level — registers immediately at import.

        Args:
            channel: Channel name without namespace, e.g. ``"order:created"``.

        Example::

            @broadcast.on("order:created")
            async def handle(data: dict) -> None:
                print(data["id"])
        """
        def decorator(func: Callable[[dict], Awaitable[None]]) -> Callable[[dict], Awaitable[None]]:
            self._driver.register(channel, func)
            return func
        return decorator

    # ── Publish ───────────────────────────────────────────────────────────────

    async def emit(self, channel: str, data: Any) -> None:
        """Publish *data* to *channel*.

        In pubsub mode: Redis PUBLISH (fire-and-forget).
        In stream mode: Redis XADD (persistent, survives restarts).

        Args:
            channel: Channel name without namespace.
            data:    Plain dict, Tortoise model, or any object with __dict__.
        """
        await self._driver.emit(channel, data)

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def connect(self, group: str | None = None, consumer: str | None = None) -> None:
        """Connect to the broker and start listening.

        For **stream mode** pass ``group`` and ``consumer``::

            await broadcast.connect(group="backend", consumer="worker-1")

        For **pubsub mode** no arguments needed::

            await broadcast.connect()

        The listen loop runs as a background task — call :meth:`disconnect`
        to stop it gracefully on shutdown.
        """
        if self._listen_task and not self._listen_task.done():
            return
        await self._driver.connect()

        if not self._driver._handlers:
            _log.info("connect(): no handlers registered — emit-only mode, listener not started")
            return

        if self._mode == "stream":
            if not group or not consumer:
                raise ValueError(
                    "stream mode requires group and consumer: "
                    "broadcast.connect(group='...', consumer='...')"
                )
            coro = self._driver.listen_stream(group, consumer)
            task_name = f"broadcast:stream:{group}:{consumer}"
        else:
            coro = self._driver.listen_pubsub()
            task_name = "broadcast:pubsub"

        self._listen_task = asyncio.create_task(coro, name=task_name)
        _log.info("listener started  task=%s", task_name)

    async def disconnect(self) -> None:
        """Stop the listener task and close the connection."""
        if self._listen_task and not self._listen_task.done():
            self._listen_task.cancel()
            try:
                await self._listen_task
            except asyncio.CancelledError:
                pass
        self._listen_task = None
        await self._driver.wait_bg_tasks()
        await self._driver.disconnect()
        _log.info("disconnected")

    # ── Manual listen (advanced) ──────────────────────────────────────────────

    async def listen(self, group: str | None = None, consumer: str | None = None) -> None:
        """Run the listen loop directly (blocking coroutine).

        Use this when you manage the task yourself::

            task = asyncio.create_task(broadcast.listen(group="backend", consumer="worker-1"))

        For most cases prefer :meth:`connect` which handles task creation automatically.
        """
        if self._mode == "stream":
            if not group or not consumer:
                raise ValueError("stream mode requires group and consumer")
            await self._driver.listen_stream(group, consumer)
        else:
            await self._driver.listen_pubsub()
