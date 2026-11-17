import pytest
from datetime import datetime, timezone
from pydantic import ValidationError

from forgeapi.schemas import BaseSchema, Schema


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
        assert schema.created_at == NOW
        assert schema.updated_at == NOW

    def test_missing_id_raises(self):
        with pytest.raises(ValidationError):
            BaseSchema(created_at=NOW, updated_at=NOW)


class TestSchema:
    def test_is_plain_pydantic_validation(self):
        class CreateUser(Schema):
            username: str
            age: int = 0

        assert CreateUser(username="bob", age="5").age == 5
        with pytest.raises(ValidationError):
            CreateUser()

    def test_changes_returns_only_sent_fields(self):
        class UpdateUser(Schema):
            username: str | None = None
            email: str | None = None

        assert UpdateUser(username="new").changes() == {"username": "new"}
        assert UpdateUser().changes() == {}

    def test_changes_keeps_an_explicit_null(self):
        class UpdateUser(Schema):
            email: str | None = None

        assert UpdateUser(email=None).changes() == {"email": None}


class TestBaseSchemaUUID:
    def test_id_accepts_int(self):
        NOW = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
        schema = BaseSchema(id=1, created_at=NOW, updated_at=NOW)
        assert schema.id == 1

    def test_id_accepts_str_uuid(self):
        import uuid
        NOW = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
        uid = str(uuid.uuid4())
        schema = BaseSchema(id=uid, created_at=NOW, updated_at=NOW)
        assert schema.id == uid


class TestBaseSchemaTimestamps:
    def test_model_without_timestamps_validates(self):
        class Tag(BaseSchema):
            name: str

        class FakeModel:
            id = 1
            name = "x"

        tag = Tag.model_validate(FakeModel())
        assert tag.created_at is None and tag.updated_at is None


from pydantic import Field  # noqa: E402


class _PostCreate(Schema):
    title: str = Field(min_length=3, max_length=10)
    views: int = Field(0, ge=0)
    tag: str | None = None


class TestPartial:
    Create = _PostCreate

    def test_all_fields_optional(self):
        Update = self.Create.partial("PostUpdate")
        assert Update.__name__ == "PostUpdate"
        assert Update().changes() == {}
        assert Update(title="abc").changes() == {"title": "abc"}

    def test_result_is_a_schema_too(self):
        assert issubclass(self.Create.partial(), Schema)

    def test_default_name(self):
        assert self.Create.partial().__name__ == "_PostCreatePartial"

    @pytest.mark.parametrize("bad", [{"title": "ab"}, {"title": "x" * 11}, {"views": -1}])
    def test_constraints_still_apply_to_given_fields(self, bad):
        with pytest.raises(ValidationError):
            self.Create.partial()(**bad)

    def test_validators_are_kept(self):
        from pydantic import field_validator

        class Named(Schema):
            name: str

            @field_validator("name")
            @classmethod
            def no_x(cls, v):
                if "x" in v:
                    raise ValueError("no x")
                return v

        with pytest.raises(ValidationError):
            Named.partial()(name="xa")

    def test_original_is_untouched(self):
        self.Create.partial()
        with pytest.raises(ValidationError):
            self.Create()

    def test_openapi_has_no_required_fields(self):
        assert "required" not in self.Create.partial().model_json_schema()


# ── changes() clears a value; update_from does not ───────────────────────────

from tortoise import Model, Tortoise, fields  # noqa: E402


class Note(Model):
    id = fields.IntField(primary_key=True)
    title = fields.CharField(max_length=50)
    body = fields.TextField(null=True)

    class Meta:
        table = "schema_notes"


class NoteCreate(Schema):
    title: str
    body: str | None = None


NoteUpdate = NoteCreate.partial("NoteUpdate")


async def test_patch_can_clear_a_value_with_changes():
    await Tortoise.init(db_url="sqlite://:memory:", modules={"models": ["tests.test_schemas"]})
    await Tortoise.generate_schemas()
    try:
        note = await Note.create(title="t", body="keep me")

        await note.update_from_dict(NoteUpdate(title="new").changes()).save()     # body not sent: untouched
        assert (await Note.get(id=note.id)).body == "keep me"

        await note.update_from_dict(NoteUpdate(body=None).changes()).save()       # body sent as null: cleared
        fresh = await Note.get(id=note.id)
        assert fresh.body is None and fresh.title == "new"
    finally:
        await Tortoise.close_connections()
