from pathlib import Path

from forgeapi.foundation import Provider
from forgeapi.logging import log

_log = log.channel("broadcasting.provider")


class BroadcastProvider(Provider):
    """Loads broadcast listeners from ``listeners_dir`` at boot time.

    Imports every module in the listeners directory so that
    ``@broadcast.on()`` decorators execute and register handlers.
    """

    def boot(self) -> None:
        listeners_dir = self.config.structure.listeners_dir
        path = Path(listeners_dir)
        if not path.exists():
            _log.debug("BroadcastProvider: no '%s' directory — skipping", listeners_dir)
            return

        import importlib
        import sys

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

        # Also import __init__.py of the listeners package
        pkg = listeners_dir.replace("/", ".").replace("\\", ".")
        if pkg not in sys.modules:
            try:
                importlib.import_module(pkg)
            except Exception:
                pass

        _log.debug("BroadcastProvider: listeners loaded from '%s'", listeners_dir)
