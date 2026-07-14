from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from forgeapi.logging import log

_log = log.channel("policies")


class Gate:
    """Policy registry and authorization entry point.

    Register a policy for a model, then call :meth:`authorize` in your
    controllers to enforce access control::

        from forgeapi.policies import gate, Policy

        @gate.policy(Post)
        class PostPolicy(Policy):
            async def update(self, user, post) -> bool:
                return post.author_id == int(user.id)

        # in the controller:
        post = await Post.find_or_fail(id)
        await gate.authorize(user, "update", post)   # raises 403 if denied
    """

    def __init__(self) -> None:
        self._policies: dict[type, type] = {}

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, model_class: type, policy_class: type) -> None:
        """Register *policy_class* as the policy for *model_class*."""
        self._policies[model_class] = policy_class

    def policy(self, model_class: type):
        """Class decorator — register the decorated class as the policy for *model_class*::

            @gate.policy(Post)
            class PostPolicy(Policy): ...
        """
        def decorator(policy_class: type) -> type:
            self.register(model_class, policy_class)
            return policy_class
        return decorator

    def discover(self, policies_dir: str) -> None:
        """Import all ``*_policy.py`` files so ``@gate.policy`` decorators execute.

        Call once at startup (or let ``Core(policies=True)`` do it)::

            gate.discover("app/policies")
        """
        path = Path(policies_dir)
        if not path.exists():
            return
        for file in sorted(path.glob("**/*_policy.py")):
            parts = file.with_suffix("").parts
            module_path = ".".join(parts)
            try:
                importlib.import_module(module_path)
            except Exception as exc:
                _log.warning("Failed to load policy file", file=str(file), error=str(exc))

    # ------------------------------------------------------------------
    # Checks
    # ------------------------------------------------------------------

    async def allows(self, user: Any, action: str, subject: Any = None) -> bool:
        """Return ``True`` if *user* is allowed to perform *action* on *subject*."""
        policy = self._policy_instance(subject)
        if policy is None:
            subject_name = type(subject).__name__ if subject is not None else "None"
            _log.warning("No policy registered", action=action, subject=subject_name)
            return False

        before = await policy.before(user, action)
        if before is not None:
            return bool(before)

        method = getattr(policy, action, None)
        if method is None:
            _log.warning("Policy has no method", policy=type(policy).__name__, action=action)
            return False

        # Actions without a model instance (e.g. create)
        if subject is None or isinstance(subject, type):
            return bool(await method(user))
        return bool(await method(user, subject))

    async def denies(self, user: Any, action: str, subject: Any = None) -> bool:
        """Inverse of :meth:`allows`."""
        return not await self.allows(user, action, subject)

    async def authorize(self, user: Any, action: str, subject: Any = None) -> None:
        """Assert *user* is allowed to perform *action* on *subject*.

        Raises ``HTTP 403`` when denied::

            await gate.authorize(user, "update", post)
            await gate.authorize(user, "create", Post)   # class — no instance needed
        """
        if not await self.allows(user, action, subject):
            raise HTTPException(status_code=403, detail="This action is unauthorized.")

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _policy_instance(self, subject: Any) -> Any | None:
        cls = subject if isinstance(subject, type) else type(subject)
        policy_class = self._policies.get(cls)
        return policy_class() if policy_class else None


gate = Gate()
