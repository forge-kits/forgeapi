from forgeapi.foundation import Provider
from forgeapi.logging import log

_log = log.channel("controllers.provider")


class ControllerProvider(Provider):
    """Auto-discovers ``*_controller.py`` files (imports user code → boot phase)."""

    def boot(self) -> None:
        from .discovery import load_controllers
        load_controllers(
            self.app,
            self.config.structure.controllers_dir,
            self.config.structure.base_prefix,
        )
        _log.debug(
            "Controllers: auto-discovered from '%s'",
            self.config.structure.controllers_dir,
        )
