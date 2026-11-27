from abc import ABC, abstractmethod
from typing import Optional, Union
from fastapi import Request


class AuthStrategy(ABC):
    """Base class for all authentication strategies.

    A strategy is a pure domain object: it extracts credentials from the
    request, verifies them, and (optionally) issues tokens or sessions.

    Layering rules:

    * Raise only :class:`~forgeapi.exceptions.ForgeAPIAuthError` subclasses
      for invalid credentials — never ``HTTPException``.  The
      :class:`~forgeapi.auth.guard.Guard` translates domain errors to HTTP.
    * Never touch user models — the guard resolves users.  A strategy that keeps
      server-side sessions does it through its own session store.
    * Declare extra capabilities by implementing the protocols in
      :mod:`forgeapi.auth.contracts` (``SessionIssuer``, ...).
    """

    #: ``WWW-Authenticate`` challenge scheme sent with 401 responses,
    #: or ``None`` to omit the header (e.g. cookie sessions).
    challenge: Optional[str] = None

    def bind(self, guard_name: str) -> None:
        """Called once by the guard that owns this strategy.  Does nothing by default."""

    @abstractmethod
    async def authenticate(self, request: Request) -> Optional[Union[str, int]]:
        """Authenticate the request.

        Returns:
            The user's identifier (primary key) on success, ``None`` if
            credentials are absent (not an error — caller decides).  The guard
            loads the user from the DB by this value.

        Raises:
            ForgeAPIAuthError: If credentials are present but invalid.
        """

    @classmethod
    def from_config(cls, cfg: dict) -> "AuthStrategy":
        """Build the strategy from a guard config dict.

        The default implementation maps config keys straight to constructor
        kwargs.  Override to handle env-var fallbacks or key renames.
        """
        return cls(**cfg)
