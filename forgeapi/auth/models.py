from __future__ import annotations

from tortoise import Model, fields


class AuthSession(Model):
    """A login session of the ``cookie`` strategy.

    The cookie holds a random token, the table holds only its SHA-256 hash, so a
    leaked table cannot be replayed as cookies.
    """

    id = fields.CharField(max_length=64, primary_key=True)
    user_id = fields.CharField(max_length=255, db_index=True)
    guard = fields.CharField(max_length=64)
    ip_address = fields.CharField(max_length=45, null=True)
    user_agent = fields.CharField(max_length=255, null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    last_activity = fields.DatetimeField()
    expires_at = fields.DatetimeField(db_index=True)

    class Meta:
        table = "auth_sessions"
