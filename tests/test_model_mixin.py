import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import HTTPException
from pydantic import BaseModel

from forgeapi.database import ModelMixin


# ---------------------------------------------------------------------------
# Fake Tortoise model for testing — no real DB needed
# ---------------------------------------------------------------------------

class FakeModel(ModelMixin):
    __name__ = "Post"

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self._saved = {}

    async def update_from_dict(self, data: dict):
        self.__dict__.update(data)

    async def save(self):
        self._saved = dict(self.__dict__)

    @classmethod
    async def get_or_none(cls, **kwargs):
        return None  # overridden per test via patch

    @classmethod
    async def create(cls, **kwargs):
        return cls(**kwargs)


class CreatePayload(BaseModel):
    title: str
    body: str
    draft: bool | None = None


class UpdatePayload(BaseModel):
    title: str | None = None
    body: str | None = None


# ---------------------------------------------------------------------------
# find_or_fail
# ---------------------------------------------------------------------------

class TestFindOrFail:
    async def test_returns_instance_when_found(self):
        instance = FakeModel(id=1, title="Hello")

        with patch.object(FakeModel, "get_or_none", new=AsyncMock(return_value=instance)):
            result = await FakeModel.find_or_fail(1)

        assert result is instance

    async def test_raises_404_when_not_found(self):
        with patch.object(FakeModel, "get_or_none", new=AsyncMock(return_value=None)):
            with pytest.raises(HTTPException) as exc_info:
                await FakeModel.find_or_fail(99)

        assert exc_info.value.status_code == 404

    async def test_404_detail_contains_model_name(self):
        with patch.object(FakeModel, "get_or_none", new=AsyncMock(return_value=None)):
            with pytest.raises(HTTPException) as exc_info:
                await FakeModel.find_or_fail(99)

        assert "FakeModel" in exc_info.value.detail

    async def test_custom_field(self):
        instance = FakeModel(slug="hello-world")

        async def fake_get_or_none(**kwargs):
            assert "slug" in kwargs
            return instance

        with patch.object(FakeModel, "get_or_none", new=AsyncMock(side_effect=fake_get_or_none)):
            result = await FakeModel.find_or_fail("hello-world", field="slug")

        assert result is instance


# ---------------------------------------------------------------------------
# create_from
# ---------------------------------------------------------------------------

class TestCreateFrom:
    async def test_creates_with_schema_data(self):
        payload = CreatePayload(title="Hello", body="World")

        created = await FakeModel.create_from(payload)

        assert created.title == "Hello"
        assert created.body == "World"

    async def test_excludes_none_fields(self):
        payload = CreatePayload(title="Hello", body="World", draft=None)

        created = await FakeModel.create_from(payload)

        assert not hasattr(created, "draft") or "draft" not in created._saved

    async def test_extra_kwargs_are_merged(self):
        payload = CreatePayload(title="Hello", body="World")

        created = await FakeModel.create_from(payload, author_id=42)

        assert created.author_id == 42

    async def test_extra_kwargs_override_schema(self):
        payload = CreatePayload(title="Old", body="Body")

        created = await FakeModel.create_from(payload, title="Overridden")

        assert created.title == "Overridden"


# ---------------------------------------------------------------------------
# update_from
# ---------------------------------------------------------------------------

class TestUpdateFrom:
    async def test_updates_provided_fields(self):
        instance = FakeModel(id=1, title="Old", body="Old body")
        payload = UpdatePayload(title="New title")

        result = await instance.update_from(payload)

        assert instance.title == "New title"

    async def test_skips_none_fields(self):
        instance = FakeModel(id=1, title="Keep", body="Keep body")
        payload = UpdatePayload(title=None, body=None)

        await instance.update_from(payload)

        assert instance.title == "Keep"
        assert instance.body == "Keep body"

    async def test_returns_self(self):
        instance = FakeModel(id=1, title="A", body="B")
        payload = UpdatePayload(title="C")

        result = await instance.update_from(payload)

        assert result is instance

    async def test_extra_kwargs_applied(self):
        instance = FakeModel(id=1, title="A", body="B")
        payload = UpdatePayload(title="New")

        await instance.update_from(payload, updated_by=7)

        assert instance.updated_by == 7

    async def test_save_called(self):
        instance = FakeModel(id=1, title="A", body="B")
        instance.save = AsyncMock()
        payload = UpdatePayload(title="New")

        await instance.update_from(payload)

        instance.save.assert_awaited_once()
