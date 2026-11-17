from __future__ import annotations

import copy
from typing import Optional, TypeVar

from pydantic import BaseModel, create_model

M = TypeVar("M", bound=BaseModel)


def partial_schema(model: type[M], name: str | None = None) -> type[M]:
    """Return a copy of *model* where every field is optional (default ``None``).

    Used by :meth:`forgeapi.schemas.Schema.partial`, which is the way to call it::

        class PostCreate(Schema):
            title: str = Field(min_length=3)
            body: str

        PostUpdate = PostCreate.partial("PostUpdate")

        PostUpdate()                 # valid, nothing to change
        PostUpdate(title="ab")       # ValidationError: too short

    Args:
        model: The schema to relax.
        name:  Class name, shown in OpenAPI.  Defaults to ``<Model>Partial``.
    """
    fields = {}
    for field_name, info in model.model_fields.items():
        relaxed = copy.copy(info)
        relaxed.default = None
        relaxed.default_factory = None
        fields[field_name] = (Optional[info.annotation], relaxed)
    return create_model(name or f"{model.__name__}Partial", __base__=model, **fields)
