from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from tortoise import fields

from .model import ModelMixin


class SoftDeleteMixin(ModelMixin):
    """Adds soft delete support to a Tortoise model.

    Sets ``deleted_at`` instead of issuing a DELETE. All default queries
    automatically exclude soft-deleted records.

    Inherit instead of (or together with) :class:`~forgeapi.database.ModelMixin`::

        from tortoise import Model, fields
        from forgeapi.database import SoftDeleteMixin

        class Post(SoftDeleteMixin, Model):
            title = fields.CharField(max_length=255)

    Instance methods::

        await post.delete()       # soft-delete — sets deleted_at
        await post.restore()      # clear deleted_at
        await post.force_delete() # permanent DELETE
        post.is_trashed           # True if deleted_at is set

    Queryset methods::

        Post.all()                    # excludes soft-deleted (default)
        Post.all().with_trashed()     # includes soft-deleted
        Post.all().only_trashed()     # only soft-deleted
        Post.filter(...).with_trashed()
    """

    deleted_at: datetime | None = fields.DatetimeField(null=True, default=None)

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if hasattr(cls, "_meta"):
            from .queryset import SoftDeleteManager
            cls._meta.manager = SoftDeleteManager(cls)

    async def delete(self, using_db=None) -> None:
        """Soft-delete: set ``deleted_at`` to now instead of deleting the row."""
        self.deleted_at = datetime.now(timezone.utc)
        await self.save(update_fields=["deleted_at"], using_db=using_db)

    async def restore(self) -> None:
        """Restore a soft-deleted record by clearing ``deleted_at``."""
        self.deleted_at = None
        await self.save(update_fields=["deleted_at"])

    async def force_delete(self, using_db=None) -> None:
        """Permanently delete the record from the database."""
        from tortoise import Model
        await Model.delete(self, using_db=using_db)

    @property
    def is_trashed(self) -> bool:
        """``True`` if this record has been soft-deleted."""
        return self.deleted_at is not None
