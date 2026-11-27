"""Factories: definition(), overrides, states, count, make, relations."""
import enum

import pytest
from tortoise import Tortoise, fields
from tortoise.exceptions import ValidationError
from tortoise.models import Model

from forgeapi.exceptions import ForgeAPIConfigError
from forgeapi.database import Factory, fake


class Role(str, enum.Enum):
    member = "member"
    admin = "admin"


class FUser(Model):
    id = fields.IntField(primary_key=True)
    email = fields.CharField(255, unique=True)
    name = fields.CharField(100)
    role = fields.CharEnumField(Role)
    bio = fields.TextField(null=True)
    karma = fields.IntField(default=5)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        app = "models"
        table = "factory_users"


class FPost(Model):
    id = fields.UUIDField(primary_key=True)
    author = fields.ForeignKeyField("models.FUser", related_name="posts")
    title = fields.CharField(40)
    published = fields.BooleanField()

    class Meta:
        app = "models"
        table = "factory_posts"


class UserFactory(Factory[FUser]):
    model = FUser

    def definition(self):
        return {"email": fake.unique.email(), "name": fake.name(), "role": Role.member}

    def admin(self):
        return self.state(role=Role.admin)


class PostFactory(Factory[FPost]):
    model = FPost

    def definition(self):
        return {"author": UserFactory(), "title": fake.sentence()[:40], "published": True}


@pytest.fixture
async def factory_db():
    await Tortoise.init(db_url="sqlite://:memory:", modules={"models": ["tests.test_factory"]})
    await Tortoise.generate_schemas()
    yield
    await Tortoise.close_connections()


async def test_create_saves_the_values_of_definition(factory_db):
    # arrange + act: nothing is passed, every value comes from definition()
    user = await UserFactory.create()

    # assert: a saved row, the e-mail looks like one, the field outside definition() keeps its default
    assert await FUser.filter(pk=user.pk).exists()
    assert "@" in user.email
    assert user.role == Role.member
    assert user.karma == 5


async def test_values_passed_to_create_win(factory_db):
    user = await UserFactory.create(name="Ann", karma=9)

    assert (user.name, user.karma) == ("Ann", 9)


async def test_state_method_is_callable_on_the_class(factory_db):
    admin = await UserFactory.admin().create()

    assert admin.role == Role.admin


async def test_count_creates_that_many_with_unique_values(factory_db):
    users = await UserFactory.count(5).create()

    assert len(users) == 5
    assert len({u.email for u in users}) == 5
    assert await FUser.all().count() == 5


async def test_make_returns_a_dict_and_saves_nothing(factory_db):
    data = await UserFactory.make(name="Ann")

    assert data["name"] == "Ann"
    assert await FUser.all().count() == 0


async def test_foreign_key_creates_the_parent(factory_db):
    post = await PostFactory.create()

    assert post.published is True
    assert await FUser.filter(pk=post.author_id).exists()
    

async def test_a_factory_passed_as_a_value_creates_that_record(factory_db):
    post = await PostFactory.create(author=UserFactory.admin())

    parent = await FUser.get(pk=post.author_id)
    assert parent.role == Role.admin
    assert await FUser.all().count() == 1


async def test_an_explicit_parent_is_not_duplicated(factory_db):
    owner = await UserFactory.create()

    await PostFactory.count(3).create(author=owner)

    assert await FUser.all().count() == 1


async def test_a_field_missing_from_definition_is_not_made_up(factory_db):
    class Bare(Factory[FUser]):
        model = FUser

    with pytest.raises(ValidationError):   # nothing fills email, name and role
        await Bare.create()


async def test_model_is_required():
    class NoModel(Factory):
        pass

    with pytest.raises(ForgeAPIConfigError):
        await NoModel.create()


def test_fake_gives_faker_values():
    assert "@" in fake.email()
