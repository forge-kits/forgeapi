from __future__ import annotations

from tortoise import Model, fields


class CacheEntry(Model):
    key = fields.CharField(max_length=255, primary_key=True)
    value = fields.TextField()
    expires_at = fields.DatetimeField(null=True, db_index=True)

    class Meta:
        table = "cache"
