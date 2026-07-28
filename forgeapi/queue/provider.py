from __future__ import annotations

import asyncio

from forgeapi.foundation import Provider
from forgeapi.logging import log

_log = log.channel("queue.provider")


class QueueProvider(Provider):
    """Runs a Queue worker in a background task.

    Activated when ``config/queue.py`` exists::

        # config/queue.py
        config = {
            "enabled": True,
            "queue": "default",  # queue name this worker processes
        }

    The provider starts ``Queue(name=...).work()`` on startup
    (an infinite poll loop) and cancels it on shutdown.

    Jobs must be dispatched via::

        from forgeapi.queue import dispatch
        await dispatch(MyJob(user_id=1))

    DB tables are created by Tortoise — add to ``config/database.py``::

        "models": ["database.models", "forgeapi.queue.models"]
    """

    _task: asyncio.Task | None = None

    def boot(self) -> None:
        cfg = self.config.queue
        if not cfg.enabled:
            _log.debug("QueueProvider: disabled via config")
            return

        self._register_lifespan(cfg.queue)

    # ------------------------------------------------------------------

    def _register_lifespan(self, queue_name: str) -> None:
        provider = self

        async def _startup() -> None:
            from .queue import Queue
            worker = Queue(name=queue_name)
            provider._task = asyncio.create_task(
                worker.work(), name=f"forgeapi:queue:{queue_name}"
            )
            _log.info("QueueProvider: worker started  queue=%s", queue_name)

        async def _shutdown() -> None:
            if provider._task and not provider._task.done():
                provider._task.cancel()
                try:
                    await provider._task
                except asyncio.CancelledError:
                    pass
            provider._task = None
            _log.info("QueueProvider: worker stopped")

        self.app.add_event_handler("startup", _startup)
        self.app.add_event_handler("shutdown", _shutdown)
        _log.debug("QueueProvider: lifespan hooks registered")
