from __future__ import annotations

from typing import TYPE_CHECKING, Any, Awaitable, Callable

if TYPE_CHECKING:
    from .manager import BroadcastManager

_instance: "BroadcastManager | None" = None


def configure(**kwargs: Any) -> "BroadcastManager":
    """Create and store the global BroadcastManager instance from config."""
    global _instance
    from .manager import BroadcastManager
    _instance = BroadcastManager(**kwargs)
    return _instance


def get() -> "BroadcastManager":
    if _instance is None:
        raise RuntimeError(
            "BroadcastManager is not configured. "
            "Add config/broadcast.py to enable broadcasting, "
            "or create a BroadcastManager instance manually."
        )
    return _instance


class _BroadcastProxy:
    """Global broadcast proxy — delegates to the configured BroadcastManager.

    Import at module level in listeners::

        from forgeapi.broadcasting import broadcast

        @broadcast.on("order:created")
        async def handle(data: dict) -> None: ...
    """

    def on(
        self, channel: str,
    ) -> Callable[[Callable[[dict], Awaitable[None]]], Callable[[dict], Awaitable[None]]]:
        return get().on(channel)

    async def emit(self, channel: str, payload: dict) -> None:
        await get().emit(channel, payload)

    async def connect(self) -> None:
        await get().connect()

    async def disconnect(self) -> None:
        await get().disconnect()

    async def run(self) -> None:
        await get().run()

    @property
    def is_configured(self) -> bool:
        return _instance is not None


broadcast = _BroadcastProxy()
