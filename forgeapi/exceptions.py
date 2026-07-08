__all__ = [
    "ForgeAPIError",
    "ForgeAPIConfigError",
    "ForgeAPIImportError",
    "ForgeAPIAuthError",
    "TokenExpiredError",
    "TokenInvalidError",
]


class ForgeAPIError(Exception):
    """Base exception for all ForgeAPI errors."""

    def __init__(self, message: str, *, hint: str = "") -> None:
        self.hint = hint
        full = f"{message}\n  Hint: {hint}" if hint else message
        super().__init__(full)


class ForgeAPIConfigError(ForgeAPIError):
    """Raised when Core or a module is misconfigured."""


class ForgeAPIImportError(ForgeAPIError, ImportError):
    """Raised when an optional dependency is not installed."""


class ForgeAPIAuthError(ForgeAPIError):
    """Base exception for authentication failures raised by auth strategies."""


class TokenExpiredError(ForgeAPIAuthError):
    """Raised when a JWT token has expired."""


class TokenInvalidError(ForgeAPIAuthError):
    """Raised when a JWT token has an invalid signature, type, or structure."""

