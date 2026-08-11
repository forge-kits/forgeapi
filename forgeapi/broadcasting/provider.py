from __future__ import annotations

import importlib
import sys
from pathlib import Path

from forgeapi.foundation import Provider
from forgeapi.logging import log

_log = log.channel("broadcasting.provider")


class BroadcastProvider(Provider):
    """Configures the global broadcast facade and wires startup/shutdown.

    Activated when ``config/broadcast.py`` exists.

    config/broadcast.py example::

        config = {
            "enabled": True,
            "driver": "redis",
            "driver_options": {
                "url": "redis://localhost:6379",
                "namespace": "myapp",
                "mode": "pubsub",
            },
        }

    Stream mode example::

        config = {
            "enabled": True,
            "driver": "redis",
            "driver_options": {
                "url": "redis://localhost:6379",
                "namespace": "myapp",
                "mode": "stream",
                "group": "backend",
                "consumer": "worker-1",
                "maxlen": 1000,
            },
        }
    """

    def register(self) -> None:
        if not self.config.provided("broadcast"):
            return
        cfg = self.config.broadcast
        if not cfg.enabled:
            _log.debug("BroadcastProvider: disabled via config")
            return
        from .facade import configure
        configure(driver=cfg.driver, **cfg.driver_options)
        _log.debug("BroadcastProvider: driver=%s", cfg.driver)

    def boot(self) -> None:
        listeners_dir = self.config.structure.listeners_dir

        if not self.config.provided("broadcast"):
            if Path(listeners_dir).exists():
                _log.warning(
                    "BroadcastProvider: listeners dir '%s' exists but "
                    "config/broadcast.py is missing — handlers will NOT run.",
                    listeners_dir,
                )
            return

        cfg = self.config.broadcast
        if not cfg.enabled:
            return

        self._load_listeners(listeners_dir)
        self._register_lifespan()

    # ------------------------------------------------------------------

    def _load_listeners(self, listeners_dir: str) -> None:
        path = Path(listeners_dir)
        if not path.exists():
            _log.debug("BroadcastProvider: no '%s' directory — skipping", listeners_dir)
            return
        for module_file in sorted(path.rglob("*.py")):
            if module_file.name.startswith("_"):
                continue
            module_path = ".".join(module_file.with_suffix("").parts)
            if module_path not in sys.modules:
                try:
                    importlib.import_module(module_path)
                    _log.debug("BroadcastProvider: loaded '%s'", module_path)
                except Exception as exc:
                    _log.error("BroadcastProvider: failed to load '%s': %s", module_path, exc)
        pkg = listeners_dir.replace("/", ".").replace("\\", ".")
        if pkg not in sys.modules:
            try:
                importlib.import_module(pkg)
            except Exception:
                pass

    def _register_lifespan(self) -> None:
        from .facade import get

        async def _startup() -> None:
            await get().connect()
            _log.info("BroadcastProvider: connected")

        async def _shutdown() -> None:
            await get().disconnect()
            _log.info("BroadcastProvider: disconnected")

        self.app.router.on_startup.append(_startup)
        self.app.router.on_shutdown.append(_shutdown)
        _log.debug("BroadcastProvider: lifespan hooks registered")
