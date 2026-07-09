import pytest
from tortoise import Tortoise, fields

from forgeapi.permissions import PermissionsMixin


class Entity(PermissionsMixin):
    id = fields.IntField(primary_key=True)
    name = fields.CharField(max_length=10)


@pytest.fixture(autouse=True)
async def init_db():
    await Tortoise.init(
        db_url="sqlite://:memory:",
        modules={
            "models": [
                "forgeapi.permissions.models",
                "tests.test_permission",
            ]
        },
    )

    await Tortoise.generate_schemas()
    yield

    await Tortoise.close_connections()


class TestPermission:

    @pytest.mark.asyncio
    async def test_assign_permission(self):
        test = await Entity.create(id=1, name="test")

        await test.assign_role("admin")
        await test.give_permission("user:read")
        assert await test.has_role("admin")
        assert await test.can("user:read")

    @pytest.mark.asyncio
    async def test_with_role(self):
        admin = await Entity.create(id=1, name="admin")
        guest = await Entity.create(id=2, name="guest")

        await admin.assign_role("admin")

        admins = await (await Entity.with_role("admin"))
        guests = await (await Entity.without_role("admin"))

        assert len(admins) == 1
        assert admins[0].id == admin.id
        assert len(guests) == 1
        assert guests[0].id == guest.id


