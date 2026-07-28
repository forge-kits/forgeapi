"""Tests for queryset pagination: paginate(), simple_paginate(), cursor_paginate()."""
import pytest
import httpx
from fastapi import FastAPI
from tortoise import Tortoise, fields
from tortoise.models import Model
from pydantic import BaseModel

from forgeapi.database.model import ModelMixin
from forgeapi.database.queryset import _encode_cursor, _decode_cursor
from forgeapi.middleware.request_context import RequestContextMiddleware
from forgeapi.pagination.paginator import Paginator
from forgeapi.pagination.response import (
    PaginatedResponse, SimplePaginatedResponse, CursorResponse,
    PaginationMeta, SimplePaginationMeta, PaginationLinks, CursorMeta,
)


# ── Test model & schema ───────────────────────────────────────────────────────

class Article(ModelMixin, Model):
    id    = fields.IntField(primary_key=True)
    title = fields.CharField(max_length=255)

    class Meta:
        table = "test_articles"


class ArticleSchema(BaseModel):
    id:    int
    title: str
    model_config = {"from_attributes": True}


# ── App factory ───────────────────────────────────────────────────────────────

def make_app(per_page: int = 5) -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestContextMiddleware)

    @app.get("/articles", response_model=None)
    async def list_articles():
        return await Article.all().order_by("id").paginate(per_page, ArticleSchema)

    @app.get("/articles/simple", response_model=None)
    async def list_simple():
        return await Article.all().order_by("id").simple_paginate(per_page, ArticleSchema)

    @app.get("/articles/cursor", response_model=None)
    async def list_cursor():
        return await Article.all().cursor_paginate(per_page, ArticleSchema, order_by="id")

    @app.get("/articles/default", response_model=None)
    async def list_default():
        # no explicit per_page — reads from ?per_page query param
        return await Article.all().order_by("id").paginate(schema=ArticleSchema)

    return app


# ── Fixtures ──────────────────────────────────────────────────────────────────

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


@pytest.fixture
async def db():
    await Tortoise.init(
        db_url="sqlite://:memory:",
        modules={"models": ["tests.test_pagination"]},
    )
    await Tortoise.generate_schemas()
    yield
    await Tortoise.close_connections()


@pytest.fixture
async def articles(db):
    for i in range(1, 13):
        await Article.create(title=f"Article {i}")


# ── Unit — cursor encode/decode ───────────────────────────────────────────────

class TestCursorEncoding:
    def test_roundtrip(self):
        payload = {"id": 42}
        assert _decode_cursor(_encode_cursor(payload)) == payload

    def test_invalid_returns_empty(self):
        assert _decode_cursor("!!!not-base64!!!") == {}

    def test_url_safe(self):
        cursor = _encode_cursor({"id": 999})
        assert "+" not in cursor
        assert "/" not in cursor


# ── Unit — Paginator config ───────────────────────────────────────────────────

class TestPaginatorConfigure:
    def test_configure_default_limit(self):
        Paginator.configure(default_limit=10, max_limit=100)
        assert Paginator.DEFAULT_LIMIT == 10

    def test_configure_max_limit(self):
        Paginator.configure(default_limit=20, max_limit=50)
        assert Paginator.MAX_LIMIT == 50

    def test_invalid_default_raises(self):
        with pytest.raises(ValueError):
            Paginator.configure(default_limit=0, max_limit=100)

    def test_default_exceeds_max_raises(self):
        with pytest.raises(ValueError, match="must not exceed"):
            Paginator.configure(default_limit=200, max_limit=100)


# ── Unit — Response models ────────────────────────────────────────────────────

class TestPaginatedResponse:
    def test_fields(self):
        meta = PaginationMeta(
            current_page=1, per_page=5, total=12, last_page=3,
            **{"from": 1, "to": 5},
        )
        resp = PaginatedResponse(data=[], meta=meta, links=PaginationLinks())
        assert resp.meta.total == 12
        assert resp.meta.last_page == 3
        assert resp.meta.from_item == 1

    def test_json_alias(self):
        meta = PaginationMeta(
            current_page=1, per_page=5, total=5, last_page=1,
            **{"from": 1, "to": 5},
        )
        dumped = meta.model_dump(by_alias=True)
        assert "from" in dumped
        assert "to" in dumped


class TestSimplePaginatedResponse:
    def test_no_total_field(self):
        meta = SimplePaginationMeta(current_page=2, per_page=5)
        resp = SimplePaginatedResponse(data=[], meta=meta, links=PaginationLinks())
        assert resp.meta.current_page == 2
        dumped = meta.model_dump()
        assert "total" not in dumped
        assert "last_page" not in dumped


class TestCursorResponse:
    def test_fields(self):
        cursor = _encode_cursor({"id": 20})
        meta = CursorMeta(per_page=5, next_cursor=cursor, prev_cursor=None)
        resp = CursorResponse(data=[], meta=meta, links=PaginationLinks())
        assert resp.meta.next_cursor == cursor
        assert resp.meta.prev_cursor is None


# ── Integration — paginate() ──────────────────────────────────────────────────

@pytest.mark.anyio
async def test_paginate_page1(articles):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=make_app()), base_url="http://test"
    ) as client:
        resp = await client.get("/articles")
    assert resp.status_code == 200
    data = resp.json()
    assert data["meta"]["total"] == 12
    assert data["meta"]["last_page"] == 3
    assert data["meta"]["current_page"] == 1
    assert data["meta"]["from"] == 1
    assert data["meta"]["to"] == 5
    assert len(data["data"]) == 5
    assert data["links"]["prev"] is None
    assert data["links"]["next"] is not None


@pytest.mark.anyio
async def test_paginate_page2(articles):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=make_app()), base_url="http://test"
    ) as client:
        resp = await client.get("/articles?page=2")
    data = resp.json()
    assert data["meta"]["current_page"] == 2
    assert len(data["data"]) == 5
    assert data["links"]["prev"] is not None
    assert data["links"]["next"] is not None


@pytest.mark.anyio
async def test_paginate_last_page(articles):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=make_app()), base_url="http://test"
    ) as client:
        resp = await client.get("/articles?page=3")
    data = resp.json()
    assert len(data["data"]) == 2
    assert data["meta"]["from"] == 11
    assert data["meta"]["to"] == 12
    assert data["links"]["next"] is None


@pytest.mark.anyio
async def test_paginate_per_page_from_query(articles):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=make_app()), base_url="http://test"
    ) as client:
        resp = await client.get("/articles/default?per_page=4")
    data = resp.json()
    assert data["meta"]["per_page"] == 4
    assert data["meta"]["last_page"] == 3


@pytest.mark.anyio
async def test_paginate_empty_table(db):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=make_app()), base_url="http://test"
    ) as client:
        resp = await client.get("/articles")
    data = resp.json()
    assert data["meta"]["total"] == 0
    assert data["meta"]["last_page"] == 1
    assert data["meta"]["from"] == 0
    assert data["meta"]["to"] == 0
    assert data["data"] == []


# ── Integration — simple_paginate() ──────────────────────────────────────────

@pytest.mark.anyio
async def test_simple_paginate_page1(articles):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=make_app()), base_url="http://test"
    ) as client:
        resp = await client.get("/articles/simple")
    data = resp.json()
    assert "total" not in data["meta"]
    assert "last_page" not in data["meta"]
    assert data["meta"]["current_page"] == 1
    assert data["meta"]["per_page"] == 5
    assert len(data["data"]) == 5
    assert data["links"]["prev"] is None
    assert data["links"]["next"] is not None


@pytest.mark.anyio
async def test_simple_paginate_last_page(articles):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=make_app()), base_url="http://test"
    ) as client:
        resp = await client.get("/articles/simple?page=3")
    data = resp.json()
    assert len(data["data"]) == 2
    assert data["links"]["next"] is None
    assert data["links"]["prev"] is not None


# ── Integration — cursor_paginate() ──────────────────────────────────────────

@pytest.mark.anyio
async def test_cursor_paginate_first_page(articles):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=make_app()), base_url="http://test"
    ) as client:
        resp = await client.get("/articles/cursor")
    data = resp.json()
    assert len(data["data"]) == 5
    assert data["data"][0]["id"] == 1
    assert data["meta"]["next_cursor"] is not None
    assert data["meta"]["prev_cursor"] is None
    assert data["links"]["next"] is not None
    assert data["links"]["prev"] is None


@pytest.mark.anyio
async def test_cursor_paginate_second_page(articles):
    app = make_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        first = (await client.get("/articles/cursor")).json()
        next_cursor = first["meta"]["next_cursor"]
        second = (await client.get(f"/articles/cursor?cursor={next_cursor}")).json()

    assert len(second["data"]) == 5
    assert second["data"][0]["id"] == 6
    assert second["meta"]["prev_cursor"] is not None
    assert second["meta"]["next_cursor"] is not None


@pytest.mark.anyio
async def test_cursor_paginate_last_page(articles):
    app = make_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        first  = (await client.get("/articles/cursor")).json()
        second = (await client.get(f"/articles/cursor?cursor={first['meta']['next_cursor']}")).json()
        third  = (await client.get(f"/articles/cursor?cursor={second['meta']['next_cursor']}")).json()

    assert len(third["data"]) == 2
    assert third["data"][0]["id"] == 11
    assert third["meta"]["next_cursor"] is None
    assert third["links"]["next"] is None
