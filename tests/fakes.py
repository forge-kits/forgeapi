"""Test doubles shared across the suite."""
from tortoise import fields
from tortoise.models import Model


class FakeSession(Model):
    """The session model ``forgeapi init`` generates, for the cookie strategy tests."""

    id = fields.CharField(max_length=64, primary_key=True)
    user_id = fields.CharField(max_length=255, db_index=True)
    guard = fields.CharField(max_length=64)
    ip_address = fields.CharField(max_length=45, null=True)
    user_agent = fields.CharField(max_length=255, null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    last_activity = fields.DatetimeField()
    expires_at = fields.DatetimeField(db_index=True)

    class Meta:
        table = "fake_sessions"


class FakeUser:
    """Stand-in for a Tortoise user model.  A guard only needs ``get_or_none``.

    Register users with ``FakeUser.users[<str id>] = FakeUser(...)``; the class
    registry is cleared by the ``fake_users`` fixture in ``conftest.py``.
    """

    users: dict[str, "FakeUser"] = {}

    def __init__(self, id, username: str | None = None) -> None:
        self.id = id
        self.username = username

    @classmethod
    async def get_or_none(cls, pk):
        return cls.users.get(str(pk))
