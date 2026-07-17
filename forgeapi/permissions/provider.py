from forgeapi.foundation import Provider
from forgeapi.logging import log

_log = log.channel("permissions.provider")


class PermissionProvider(Provider):
    """Wires the RBAC pivot tables to the user model.

    Pure convention: scans ``models_dir`` for the single model inheriting
    ``PermissionsMixin`` and silently skips when there is none — inheriting
    the mixin is what activates the module.  Imports user code → boot phase.
    """

    def boot(self) -> None:
        from .discovery import find_permissions_model
        model = find_permissions_model(self.config.structure.models_dir, required=False)
        if model is None:
            _log.debug("Permissions: no PermissionsMixin model in models_dir — skipping")
            return

        from .registry import setup_permissions
        setup_permissions(user_model=model)
        _log.debug("Permissions: enabled for model '%s'", model.__name__)
