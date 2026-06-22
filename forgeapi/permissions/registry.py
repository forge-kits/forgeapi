from typing import Optional, Type

_user_model: Optional[Type] = None


def setup_permissions(user_model: Type) -> None:
    """Register the User model so permission dependencies can fetch DB users.

    Call once in main.py after defining your User model::

        from forgeapi.permissions import setup_permissions
        from app.models import User

        setup_permissions(user_model=User)

    Or pass via Core::

        core = Core(app, auth=True, permissions=User)
    """
    global _user_model
    _user_model = user_model


def get_user_model() -> Type:
    if _user_model is None:
        raise RuntimeError(
            "User model not registered. "
            "Call setup_permissions(user_model=User) or Core(..., permissions=User)."
        )
    return _user_model
