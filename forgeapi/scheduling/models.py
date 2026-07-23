from tortoise import Model, fields


class ScheduledTask(Model):
    name = fields.CharField(max_length=255, unique=True)
    schedule_type = fields.CharField(max_length=20)
    schedule_config = fields.JSONField(default=dict)
    is_enabled = fields.BooleanField(default=True)
    next_run_at = fields.DatetimeField(null=True)
    last_run_at = fields.DatetimeField(null=True)
    last_status = fields.CharField(max_length=20, null=True)
    last_error = fields.TextField(null=True)

    class Meta:
        table = "scheduled_tasks"
