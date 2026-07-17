from __future__ import annotations

from forgeapi.foundation import Provider, import_string
from forgeapi.logging import log

_log = log.channel("auth.provider")


class AuthProvider(Provider):
    """Builds guards from the ``auth`` config section and registers them on the facade.

    Runs in the boot phase: guard configs may name user models
    (``"model": "database.models.user.User"``), and importing user code
    belongs in boot.
    """

    def boot(self) -> None:
        from forgeapi.exceptions import ForgeAPIConfigError
        from .facade import auth as facade
        from .guard import Guard

        guards = self.config.auth.guards
        if not guards:
            raise ForgeAPIConfigError(
                "config/auth.py exists but defines no guards.",
                hint=(
                    'Add at least one guard: config = {"default": "api", '
                    '"guards": {"api": {"strategy": "jwt", "secret": env("JWT_SECRET")}}}'
                ),
            )

        for name, guard_cfg in guards.items():
            guard_cfg = dict(guard_cfg)
            strategy_name = guard_cfg.pop("strategy", "jwt")
            model = guard_cfg.pop("model", None)
            if isinstance(model, str):
                model = import_string(model)
            if strategy_name == "telegram":
                guard_cfg.setdefault("debug", self.config.project.debug)

            strategy = facade.create_strategy(strategy_name, guard_cfg)
            facade.register(name, Guard(name=name, strategy=strategy, user_model=model))
            _log.debug("Auth: guard '%s' ready", name, strategy=strategy_name)

        facade.set_default(self.config.auth.default)
