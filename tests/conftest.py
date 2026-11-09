import pytest
from tortoise import Tortoise, fields
from forgeapi.pagination.paginator import Paginator
from forgeapi.permissions import PermissionsMixin


# ── Permissions test model ────────────────────────────────────────────────────

class UserModel(PermissionsMixin):
    id = fields.IntField(primary_key=True)

    class Meta:
        table = "test_perm_users"


# ── Pagination reset ──────────────────────────────────────────────────────────

# Restrict anyio async tests to asyncio only (trio has incompatible version installed)
@pytest.fixture(params=["asyncio"])
def anyio_backend(request):
    return request.param


@pytest.fixture(autouse=True)
def reset_paginator():
    default = Paginator.DEFAULT_LIMIT
    maximum = Paginator.MAX_LIMIT
    yield
    Paginator.DEFAULT_LIMIT = default
    Paginator.MAX_LIMIT = maximum


# ── DB fixtures for test_permissions.py ──────────────────────────────────────

@pytest.fixture
async def db():
    await Tortoise.init(
        db_url="sqlite://:memory:",
        modules={
            "models": [
                "forgeapi.permissions.models",
                "tests.conftest",
            ]
        },
    )
    await Tortoise.generate_schemas()
    yield
    await Tortoise.close_connections()


@pytest.fixture
async def user(db):
    return await UserModel.create(id=1)


@pytest.fixture
async def other_user(db):
    return await UserModel.create(id=2)


@pytest.fixture(autouse=True)
def fake_users():
    """Reset the FakeUser registry around every test."""
    from tests.fakes import FakeUser
    FakeUser.users.clear()
    yield FakeUser.users
    FakeUser.users.clear()
