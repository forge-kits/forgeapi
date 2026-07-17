from forgeapi.foundation import Provider
from forgeapi.logging import log

_log = log.channel("telescope.provider")


class TelescopeProvider(Provider):
    """Activates the Telescope debug inspector. Never enable in production."""

    def register(self) -> None:
        _log.warning(
            "ForgeAPI running in DEBUG mode — "
            "Telescope active at /_forge/telescope/requests. "
            "Do not use in production."
        )
        from . import setup_telescope
        setup_telescope(self.app)
