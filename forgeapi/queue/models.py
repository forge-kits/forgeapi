from __future__ import annotations

from tortoise import Model, fields
from tortoise.signals import pre_save


class JobRecord(Model):
    id = fields.BigIntField(primary_key=True)
    queue = fields.CharField(max_length=255, default="default")
    payload = fields.JSONField()
    attempts = fields.SmallIntField(default=0)
    reserved_at = fields.DatetimeField(null=True)
    available_at = fields.DatetimeField()
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "queued_jobs"


class FailedJob(Model):
    id = fields.BigIntField(primary_key=True)
    uuid = fields.UUIDField(unique=True)
    queue = fields.CharField(max_length=255, default="default")
    payload = fields.JSONField()
    exception = fields.TextField()
    failed_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "failed_jobs"


@pre_save(FailedJob)
async def _set_uuid(sender, instance, using_db, update_fields) -> None:
    if not instance.uuid:
        import uuid
        instance.uuid = uuid.uuid4()
