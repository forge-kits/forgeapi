import logging
from typing import Optional, Type

from forgeapi.exceptions import ForgeAPIConfigError

logger = logging.getLogger("forgeapi.permissions")

_user_model: Optional[Type] = None


def setup_permissions(user_model: Type) -> None:
    global _user_model
    _user_model = user_model
    logger.debug("Permissions: user model registered as '%s'", user_model.__name__)


def get_user_model() -> Type:
    if _user_model is None:
        raise ForgeAPIConfigError(
            "User model not registered.",
            hint=(
                "Pass the model to Core: Core(app, permissions=User)  "
                "or enable auto-detection: Core(app, permissions=True)."
            ),
        )
    return _user_model
