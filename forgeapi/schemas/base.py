from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class BaseSchema(BaseModel):
    """Base response schema — reads from a Tortoise model via ``from_attributes``.

    Inherit to add your own response fields::

        class UserSchema(BaseSchema):
            username: str
            email: str
    """

    id: int
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

    All fields should be ``Optional`` so partial updates work::

        class UserUpdateSchema(BaseUpdateSchema):
            username: str | None = None
            email: str | None = None
    """
