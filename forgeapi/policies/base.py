from __future__ import annotations

from typing import Any


class Policy:
    """Base class for resource policies.

    Subclass and define async methods matching action names::

        class PostPolicy(Policy):
            async def view(self, user, post) -> bool:
                return True

            async def create(self, user) -> bool:
                return user is not None

            async def update(self, user, post) -> bool:
                return post.author_id == int(user.id)

            async def delete(self, user, post) -> bool:
                return post.author_id == int(user.id)

    Override ``before`` for blanket checks (e.g. admin bypass)::

        async def before(self, user, action: str) -> bool | None:
            if await user.has_role("admin"):
                return True
            return None  # continue to specific method
    """

    async def before(self, user: Any, action: str) -> bool | None:
        """Called before any policy method.

        Return ``True`` / ``False`` to short-circuit.
        Return ``None`` to proceed to the specific action method.
        """
        return None
