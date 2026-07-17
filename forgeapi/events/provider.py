from pathlib import Path

from forgeapi.foundation import Provider
from forgeapi.logging import log

_log = log.channel("events.provider")


class EventProvider(Provider):
    """Loads event listeners from ``listeners_dir`` (imports user code → boot phase).

    Convention-based: silently skips when the directory does not exist.
    """

    def boot(self) -> None:
        listeners_dir = self.config.structure.listeners_dir
        if not Path(listeners_dir).exists():
            _log.debug("Events: no '%s' directory — skipping", listeners_dir)
            return
        from .bus import EventBus
        EventBus.get_instance().load_from_dir(listeners_dir)
        _log.debug("Events: listeners loaded from '%s'", listeners_dir)
