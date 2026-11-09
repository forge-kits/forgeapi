"""Test doubles shared across the suite."""


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
