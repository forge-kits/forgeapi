import asyncio
import importlib
from typing import Any, Awaitable, Callable

from forgeapi.logging import log

_log = log.channel("broadcasting")

_REGISTRY: dict[str, str] = {
    "redis": "forgeapi.broadcasting.drivers.redis.RedisDriver",
}


def register_driver(name: str, import_path: str) -> None:
    """Register a custom broadcast driver.

    Args:
        name:        Driver alias used in config (e.g. ``"rabbitmq"``).
        import_path: Dotted path to the driver class
                     (e.g. ``"myapp.broadcasting.RabbitMQDriver"``).
    """
    _REGISTRY[name] = import_path


class BroadcastManager:
    """Driver-agnostic broadcast manager.

    All driver-specific options (url, mode, group, consumer, etc.) go into
    ``driver_options`` and are forwarded as-is to the driver constructor.

    Example::

        broadcast = BroadcastManager(
            driver="redis",
            url="redis://localhost:6379",
            namespace="shop",
            mode="stream",
            group="backend",
            consumer="worker-1",
        )

        @broadcast.on("order:created")
        async def handle(data: dict) -> None:
            print(data["id"])

        async with lifespan(app):
            await broadcast.connect()
            yield
            await broadcast.disconnect()
    """

    def __init__(self, driver: str = "redis", **driver_options: Any) -> None:
        self._driver = self._make_driver(driver, **driver_options)
        self._listen_task: asyncio.Task | None = None

    def _make_driver(self, name: str, **options: Any):
        if name not in _REGISTRY:
            raise ValueError(
                f"Unknown broadcast driver '{name}'. "
                f"Available: {list(_REGISTRY)}. "
                "Register custom drivers with register_driver()."
            )
        module_path, cls_name = _REGISTRY[name].rsplit(".", 1)
        module = importlib.import_module(module_path)
        return getattr(module, cls_name)(**options)

    # ── Registration ──────────────────────────────────────────────────────────

    def on(
        self, channel: str,
    ) -> Callable[[Callable[[dict], Awaitable[None]]], Callable[[dict], Awaitable[None]]]:
        """Register an async handler for *channel*.

        Use as a decorator at module level — registers immediately at import::

            @broadcast.on("order:created")
            async def handle(data: dict) -> None:
                print(data["id"])
        """
        def decorator(func: Callable[[dict], Awaitable[None]]) -> Callable[[dict], Awaitable[None]]:
            self._driver.register(channel, func)
            return func
        return decorator

    # ── Emit ──────────────────────────────────────────────────────────────────

    async def emit(self, channel: str, payload: dict) -> None:
        """Publish *payload* to *channel*.

        Args:
            channel: Channel name without namespace.
            payload: Plain dict.
        """
        await self._driver.emit(channel, payload)

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def connect(self) -> None:
        """Connect to the broker and start the listener task.

        No-op if already connected. If no handlers are registered the
        connection is opened in emit-only mode (no listener task started).
        """
        if self._listen_task and not self._listen_task.done():
            return
        await self._driver.connect()
        if not self._driver.has_listeners:
            _log.info("connect(): no handlers registered — emit-only mode")
            return
        self._listen_task = asyncio.create_task(
            self._driver.listen(), name="broadcast:listener"
        )
        _log.info("listener started")

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

    async def listen(self) -> None:
        """Run the listen loop directly (blocking coroutine).

        For most cases prefer :meth:`run`.
        """
        await self._driver.listen()

    async def run(self) -> None:
        """Connect and run the listener in the foreground (blocking).

        Use this in standalone asyncio scripts — errors propagate naturally,
        Ctrl+C cancels cleanly::

            async def main() -> None:
                await broadcast.run()

            asyncio.run(main())
        """
        await self._driver.connect()
        try:
            await self._driver.listen()
        finally:
            await self._driver.wait_bg_tasks()
            await self._driver.disconnect()
