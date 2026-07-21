from __future__ import annotations

from typing import Any, TYPE_CHECKING

from fastapi import HTTPException

if TYPE_CHECKING:
    from pydantic import BaseModel as PydanticModel
    from .observer import ModelObserver


class ModelMixin:
    """Mixin for Tortoise models — adds convenience shortcuts.

    Inherit alongside ``tortoise.Model``::

        from tortoise import Model, fields
        from forgeapi.database import ModelMixin

        class Post(ModelMixin, Model):
            title = fields.CharField(max_length=255)
    """

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        # After Tortoise sets up _meta, inject ForgeManager so .paginate() is available
        # on every queryset: Post.filter(...).paginate(request, schema)
        if hasattr(cls, "_meta") and "objects" not in cls.__dict__:
            from .queryset import ForgeManager
            cls._meta.manager = ForgeManager(cls)

    # ------------------------------------------------------------------
    # Class methods
    # ------------------------------------------------------------------

    @classmethod
    async def find_or_fail(cls, id: Any, field: str = "id") -> "ModelMixin":
        """Fetch a record by *id* or raise HTTP 404.

        Args:
            id:    The lookup value.
            field: Column to filter by (default ``"id"``).

        Raises:
            HTTPException: 404 if the record does not exist.

        Example::

            post = await Post.find_or_fail(id)
        """
        obj = await cls.get_or_none(**{field: id})
        if obj is None:
            name = cls.__name__
            raise HTTPException(status_code=404, detail=f"{name} not found.")
        return obj

    @classmethod
    async def create_from(cls, payload: "PydanticModel", **extra: Any) -> "ModelMixin":
        """Create a record from a Pydantic schema instance.

        Equivalent to ``Model.create(**payload.model_dump(), **extra)``.
        ``None`` values from the schema are excluded so optional fields
        without a value don't overwrite database defaults.

        Args:
            payload: A Pydantic model instance (e.g. a ``BaseCreateSchema``).
            **extra: Additional field values merged after the schema dump
                     (useful for server-set fields like ``author_id``).

        Example::

            post = await Post.create_from(payload, author_id=user.id)
        """
        data = payload.model_dump(exclude_none=True)
        data.update(extra)
        return await cls.create(**data)

    # ------------------------------------------------------------------
    # Instance methods
    # ------------------------------------------------------------------

    @classmethod
    def observe(cls, observer: "ModelObserver | type[ModelObserver]") -> None:
        """Register an observer for this model's lifecycle events.

        Accepts either a class (auto-instantiated) or an instance::

            Post.observe(PostObserver)    # class — instantiated automatically
            Post.observe(PostObserver())  # or pass an instance directly

        Args:
            observer: A :class:`~forgeapi.database.observer.ModelObserver`
                subclass or instance. Only the methods you define are called.
        """
        from .observer import _register_observer, ModelObserver as _Base
        if isinstance(observer, type) and issubclass(observer, _Base):
            observer = observer()
        _register_observer(cls, observer)

    async def update_from(self, payload: "PydanticModel", **extra: Any) -> "ModelMixin":
        """Update this instance from a Pydantic schema and save.

        Only fields explicitly set by the client are applied — ``None``
        values are skipped so partial PATCH payloads work correctly.

        Args:
            payload: A Pydantic model instance (e.g. a ``BaseUpdateSchema``).
            **extra: Additional field overrides applied after the schema.

        Returns:
            ``self`` — the updated instance.

        Example::

            await post.update_from(payload)
            await post.update_from(payload, updated_by=user.id)
        """
        data = payload.model_dump(exclude_none=True)
        data.update(extra)
        await self.update_from_dict(data)
        await self.save()
        return self
