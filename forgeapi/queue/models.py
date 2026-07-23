from __future__ import annotations

import uuid as uuid_module
from tortoise import Model, fields


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
    uuid = fields.CharField(max_length=36, default=lambda: str(uuid_module.uuid4()))
    queue = fields.CharField(max_length=255, default="default")
    payload = fields.JSONField()
    exception = fields.TextField()
    failed_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "failed_jobs"
