import logging
from typing import Optional, Type

from forgeapi.exceptions import ForgeAPIConfigError

logger = logging.getLogger("forgeapi.permissions")

_user_model: Optional[Type] = None


def setup_permissions(user_model: Type) -> None:
    """Register the application's user model for the permissions system.

    Must be called once at startup (automatically done by ``Core`` when
    ``permissions=`` is provided).  Subsequent calls overwrite the previous
    registration — useful in tests that need to swap models.

    Args:
        user_model: The Tortoise model class that inherits
                    :class:`~forgeapi.permissions.PermissionsMixin`.

    Example::

        from forgeapi.permissions import setup_permissions
        from myapp.models import User

        setup_permissions(User)

        # Typically done via Core instead:
        # Core(app, permissions=User)
    """
    global _user_model
    _user_model = user_model
    logger.debug("Permissions: user model registered as '%s'", user_model.__name__)


def get_user_model() -> Type:
    """Return the registered user model class.

    Raises:
        ForgeAPIConfigError: If :func:`setup_permissions` has not been called yet.

    Returns:
        The Tortoise model class previously registered via
        :func:`setup_permissions`.

    Example::

        from forgeapi.permissions.registry import get_user_model

        UserModel = get_user_model()
        user = await UserModel.get(id=1)
    """
    if _user_model is None:
        raise ForgeAPIConfigError(
            "User model not registered.",
            hint=(
                "Pass the model to Core: Core(app, permissions=User)  "
                "or enable auto-detection: Core(app, permissions=True)."
            ),
        )
    return _user_model
