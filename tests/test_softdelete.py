from __future__ import annotations

import pytest
from tortoise import Tortoise, fields, Model

from forgeapi.database import SoftDeleteMixin


class Article(SoftDeleteMixin, Model):
    title = fields.CharField(max_length=255)

    class Meta:
        table = "test_articles"


@pytest.fixture
async def db():
    await Tortoise.init(
        db_url="sqlite://:memory:",
        modules={"models": ["tests.test_softdelete"]},
    )
    await Tortoise.generate_schemas()
    yield
    await Tortoise.close_connections()


@pytest.fixture
async def article(db):
    return await Article.create(title="Hello")


class TestSoftDelete:
    async def test_delete_sets_deleted_at(self, article):
        assert article.deleted_at is None
        await article.delete()
        assert article.deleted_at is not None

    async def test_is_trashed(self, article):
        assert not article.is_trashed
        await article.delete()
        assert article.is_trashed

    async def test_deleted_excluded_from_all(self, article):
        await article.delete()
        assert await Article.all().count() == 0

    async def test_deleted_excluded_from_filter(self, article):
        await article.delete()
        assert await Article.filter(title="Hello").count() == 0

    async def test_with_trashed_includes_deleted(self, article):
        await article.delete()
        assert await Article.all().with_trashed().count() == 1

    async def test_only_trashed_returns_deleted_only(self, db):
        alive = await Article.create(title="Alive")
        dead = await Article.create(title="Dead")
        await dead.delete()

        result = await Article.all().only_trashed()
        titles = [r.title for r in result]
        assert "Dead" in titles
        assert "Alive" not in titles

    async def test_restore_clears_deleted_at(self, article):
        await article.delete()
        await article.restore()
        assert article.deleted_at is None
        assert await Article.all().count() == 1

    async def test_force_delete_removes_row(self, article):
        await article.force_delete()
        assert await Article.all().with_trashed().count() == 0

    async def test_find_or_fail_excludes_deleted(self, article):
        from fastapi import HTTPException
        await article.delete()
        with pytest.raises(HTTPException) as exc:
            await Article.find_or_fail(article.id)
        assert exc.value.status_code == 404
