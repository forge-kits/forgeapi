"""ForgeAPI Telescope — in-memory request inspector.

Activated automatically when ``Core(app, debug=True)``.

WebSocket endpoint (only in debug mode):
    WS     /_forge/telescope/ws       — live stream; sends init/entry/clear JSON messages
    DELETE /_forge/telescope/requests — clear store

Recording a job execution from a custom job system::

    from forgeapi.telescope import record_job

    record_job("SendEmailJob", status="done", attempts=1, duration_ms=45.2)
    record_job("ProcessPayment", status="failed", attempts=3, error="Timeout")
"""

from __future__ import annotations

import logging

from .store import DebugStore, JobRecord

logger = logging.getLogger("forgeapi.telescope")

__all__ = ["setup_telescope", "DebugStore", "record_job"]


def record_job(
    job: str,
    status: str,
    attempts: int = 1,
    duration_ms: float | None = None,
    error: str | None = None,
) -> None:
    """Attach a job execution record to the active request entry.

    Call this from your job dispatcher/runner so Telescope shows
    which jobs were triggered during a request.

    Args:
        job:         Job class name or identifier.
        status:      ``"queued"`` | ``"running"`` | ``"done"`` | ``"failed"``.
        attempts:    Number of attempts made.
        duration_ms: Execution time in milliseconds (``None`` if not finished).
        error:       Exception message if ``status == "failed"``.
    """
    from .context import get_current
    entry = get_current()
    if entry is not None:
        entry.jobs.append(JobRecord(
            job=job,
            status=status,
            attempts=attempts,
            duration_ms=duration_ms,
            error=error,
        ))


def setup_telescope(app) -> None:
    """Install all Telescope hooks and mount the router on *app*.

    Called automatically by ``Core`` when ``debug=True``.
    Safe to call multiple times — hooks are idempotent.
    """
    from .middleware import DebugMiddleware
    from .hooks.logging_hook import install_logging_hook
    from .hooks.events_hook import install_events_hook
    from .hooks.tortoise_hook import install_tortoise_hook
    from .router import router

    app.add_middleware(DebugMiddleware)
    logger.debug("Telescope: request capture middleware registered")

    install_logging_hook()
    install_events_hook()
    install_tortoise_hook()

    app.include_router(router)
    logger.debug("Telescope: endpoints mounted at /_forge/telescope/requests")
