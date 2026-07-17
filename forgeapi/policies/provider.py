from forgeapi.foundation import Provider
from forgeapi.logging import log

_log = log.channel("policies.provider")


class PolicyProvider(Provider):
    """Discovers ``*_policy.py`` files (imports user code → boot phase)."""

    def boot(self) -> None:
        from .gate import gate
        gate.discover(self.config.structure.policies_dir)
        _log.debug("Policies: discovered from '%s'", self.config.structure.policies_dir)
