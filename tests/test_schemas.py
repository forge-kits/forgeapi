import pytest
from datetime import datetime, timezone
from pydantic import ValidationError

from forgeapi.schemas import BaseSchema, BaseCreateSchema, BaseUpdateSchema


NOW = datetime.now(timezone.utc)


class TestBaseSchema:
    def test_valid_data(self):
        class UserSchema(BaseSchema):
            username: str

        user = UserSchema(id=1, created_at=NOW, updated_at=NOW, username="alice")
        assert user.id == 1
        assert user.username == "alice"

    def test_missing_required_field_raises(self):
        class UserSchema(BaseSchema):
            username: str

        with pytest.raises(ValidationError):
            UserSchema(id=1, created_at=NOW, updated_at=NOW)

    def test_from_attributes_enabled(self):
        class UserSchema(BaseSchema):
            pass

        class FakeModel:
            id = 42
            created_at = NOW
            updated_at = NOW

        schema = UserSchema.model_validate(FakeModel())
        assert schema.id == 42

    def test_missing_id_raises(self):
        with pytest.raises(ValidationError):
            BaseSchema(created_at=NOW, updated_at=NOW)


class TestBaseCreateSchema:
    def test_empty_is_valid(self):
        schema = BaseCreateSchema()
        assert schema is not None

    def test_custom_fields(self):
        class CreateUser(BaseCreateSchema):
            username: str
            email: str

        user = CreateUser(username="bob", email="bob@example.com")
        assert user.username == "bob"

    def test_missing_required_custom_field(self):
        class CreateUser(BaseCreateSchema):
            username: str

        with pytest.raises(ValidationError):
            CreateUser()


class TestBaseUpdateSchema:
    def test_empty_is_valid(self):
        schema = BaseUpdateSchema()
        assert schema is not None

    def test_optional_fields(self):
        class UpdateUser(BaseUpdateSchema):
            username: str | None = None
            email: str | None = None

        schema = UpdateUser()
        assert schema.username is None
        assert schema.email is None

    def test_partial_update(self):
        class UpdateUser(BaseUpdateSchema):
            username: str | None = None
            email: str | None = None

        schema = UpdateUser(username="new_name")
        assert schema.username == "new_name"
        assert schema.email is None
