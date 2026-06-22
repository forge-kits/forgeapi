from abc import ABC, abstractmethod
from typing import Optional
from fastapi import Request

from ..models import AuthUser


class AuthStrategy(ABC):
    """Base class for all authentication strategies.

    Implement :meth:`authenticate` to support a new auth mechanism.
    """

    @abstractmethod
    async def authenticate(self, request: Request) -> Optional[AuthUser]:
        """Authenticate the request.

        Returns:
            :class:`~forgeapi.auth.models.AuthUser` on success,
            ``None`` if credentials are absent (not an error — caller decides).
        """
