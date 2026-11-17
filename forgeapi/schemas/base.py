from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel

from .partial import partial_schema


class Schema(BaseModel):
    """Base for input schemas (request bodies): a Pydantic model plus two helpers.

    ::

        class PostCreate(Schema):
            title: str
            body: str | None = None

        PostUpdate = PostCreate.partial("PostUpdate")   # PATCH body: every field optional

    Everything else is plain Pydantic: field types, ``Field(...)`` constraints and
    validators work as documented by Pydantic.
    """

    @classmethod
    def partial(cls, name: str | None = None) -> type["Schema"]:
        """A copy of this schema where every field is optional (default ``None``).

        Constraints and validators stay and run only for the fields the client sends.
        The original schema is not changed.

        Args:
            name: Class name shown in OpenAPI.  Defaults to ``<Class>Partial``.
        """
        return partial_schema(cls, name)

    def changes(self) -> dict[str, Any]:
        """Only the fields the client actually sent (``model_dump(exclude_unset=True)``).

        Unlike ``None``-filtering, a field sent as ``null`` is kept, so a PATCH can clear a value::

            await post.update_from_dict(payload.changes())
            await post.save()
        """
        return self.model_dump(exclude_unset=True)


class BaseSchema(BaseModel):
    """Base response schema: reads from a Tortoise model via ``from_attributes``.

    ``id`` is required, ``created_at`` / ``updated_at`` are filled when the model has them.
    Inherit to add your own response fields::

        class UserResponse(BaseSchema):
            username: str
            email: str
    """

    id: int | str
    #: Optional so a model without timestamp columns still validates.
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}
