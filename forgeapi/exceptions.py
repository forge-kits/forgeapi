__all__ = [
    "ForgeAPIError",
    "ForgeAPIConfigError",
    "ForgeAPIImportError",
    "ForgeAPIAuthError",
    "TokenExpiredError",
    "TokenInvalidError",
    "SessionExpiredError",
    "SessionInvalidError",
    "UserNotFoundError",
]


class ForgeAPIError(Exception):
    """Base exception for all ForgeAPI errors."""

    status_code: int = 500

    def __init__(self, message: str, *, hint: str = "", status_code: int | None = None) -> None:
        self.hint = hint
        if status_code is not None:
            self.status_code = status_code
        full = f"{message}\n  Hint: {hint}" if hint else message
        super().__init__(full)


class ForgeAPIConfigError(ForgeAPIError):
    """Raised when Core or a module is misconfigured."""


class ForgeAPIImportError(ForgeAPIError, ImportError):
    """Raised when an optional dependency is not installed."""

    status_code: int = 501


class ForgeAPIAuthError(ForgeAPIError):
    """Base exception for authentication failures raised by auth strategies.

    Strategies raise these domain exceptions; :class:`~forgeapi.auth.guard.Guard`
    is the single place that translates them to HTTP 401 responses.
    ``code`` is a machine-readable identifier exposed in the
    ``WWW-Authenticate`` challenge.
    """

    status_code: int = 401
    code: str = "auth_error"


class TokenExpiredError(ForgeAPIAuthError):
    """Raised when a token has expired."""

    code = "token_expired"


class TokenInvalidError(ForgeAPIAuthError):
    """Raised when a token has an invalid signature, type, or structure."""

    code = "token_invalid"


class SessionExpiredError(ForgeAPIAuthError):
    """Raised when a session cookie has expired."""

    code = "session_expired"


class SessionInvalidError(ForgeAPIAuthError):
    """Raised when a session cookie is malformed or its signature does not match."""

    code = "session_invalid"


class UserNotFoundError(ForgeAPIAuthError):
    """Raised when credentials are valid but the user no longer exists in the DB."""

    code = "user_not_found"
