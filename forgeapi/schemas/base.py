from datetime import datetime
from pydantic import BaseModel


class BaseSchema(BaseModel):
    """Base response schema — reads from a Tortoise model via ``from_attributes``.

    Inherit to add your own response fields::

        class UserSchema(BaseSchema):
            username: str
            email: str
    """

    id: int | str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class BaseCreateSchema(BaseModel):
    """Base schema for POST (create) payloads.

    All fields should be required::

        class UserCreateSchema(BaseCreateSchema):
            username: str
            email: str
    """


class BaseUpdateSchema(BaseModel):
    """Base schema for PATCH (update) payloads.

    All fields **must** be ``Optional`` with a ``None`` default so partial
    updates work — the framework only persists fields that are explicitly
    provided by the client.  Declaring a required (non-optional) field is a
    bug and is caught at class-definition time::

        class UserUpdateSchema(BaseUpdateSchema):
            username: str | None = None
            email: str | None = None
    """

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        # Pydantic sets model_fields AFTER __init_subclass__ returns, so we
        # inspect the raw class annotations instead.  A field declared without
        # a default value has an entry in __annotations__ but NOT in __dict__.
        own_annotations = cls.__dict__.get("__annotations__", {})
        for field_name in own_annotations:
            if field_name.startswith("_"):
                continue
            if field_name not in cls.__dict__:
                raise TypeError(
                    f"{cls.__name__}.{field_name} must be Optional[...] = None. "
                    f"BaseUpdateSchema subclasses represent PATCH payloads — "
                    f"all fields must be optional to support partial updates."
                )
