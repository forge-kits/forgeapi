from __future__ import annotations

import logging
from typing import Any


class Logger:
    """Structured logger — kwargs-based context, named channels.

    Wraps Python's standard ``logging`` so existing handlers (file, syslog,
    third-party integrations) keep working unchanged.

    Internal forge-kits use::

        from forgeapi.logging import log

        log.debug("Guard authenticated", guard="api", user_id=42)
        log.error("Strategy failed", error=str(e))

    User project use::

        from forgeapi import Log

        Log.info("Order created", order_id=order.id, user_id=user.id)
        Log.error("Payment failed", order_id=order.id, reason=str(e))

    Named channels::

        auth_log = Log.channel("auth")
        auth_log.debug("Token decoded", user_id=42)
    """

    def __init__(self, name: str) -> None:
        self._name = name
        self._inner = logging.getLogger(name)

    # ------------------------------------------------------------------
    # Channel
    # ------------------------------------------------------------------

    def channel(self, name: str) -> Logger:
        """Return a child logger named ``<parent>.<name>``.

        Example::

            _log = log.channel("auth.guard")
            _log.debug("401", path="/me")
        """
        return Logger(f"{self._name}.{name}")

    # ------------------------------------------------------------------
    # Log levels
    # ------------------------------------------------------------------

    def debug(self, message: str, *args: Any, **ctx: Any) -> None:
        if self._inner.isEnabledFor(logging.DEBUG):
            self._emit(logging.DEBUG, message, args, ctx)

    def info(self, message: str, *args: Any, **ctx: Any) -> None:
        if self._inner.isEnabledFor(logging.INFO):
            self._emit(logging.INFO, message, args, ctx)

    def warning(self, message: str, *args: Any, **ctx: Any) -> None:
        self._emit(logging.WARNING, message, args, ctx)

    def error(self, message: str, *args: Any, **ctx: Any) -> None:
        self._emit(logging.ERROR, message, args, ctx)

    def critical(self, message: str, *args: Any, **ctx: Any) -> None:
        self._emit(logging.CRITICAL, message, args, ctx)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _emit(self, level: int, message: str, args: tuple, ctx: dict) -> None:
        if args:
            try:
                message = message % args
            except (TypeError, ValueError):
                message = f"{message} {args}"
        if ctx:
            message = message + " | " + "  ".join(f"{k}={v!r}" for k, v in ctx.items())
        self._inner.log(level, message)
