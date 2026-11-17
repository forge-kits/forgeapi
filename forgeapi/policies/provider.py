from forgeapi.config.layout import layout
from forgeapi.foundation import Provider
from forgeapi.logging import log

_log = log.channel("policies.provider")


class PolicyProvider(Provider):
    """Discovers ``*_policy.py`` files (imports user code → boot phase)."""

    def boot(self) -> None:
        from .gate import gate
        gate.discover(layout.policies_dir)
        _log.debug("Policies: discovered from '%s'", layout.policies_dir)
