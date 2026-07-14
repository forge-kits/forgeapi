import base64
import json
import pytest
import httpx
from fastapi import FastAPI
from starlette.requests import Request

from forgeapi.pagination.paginator import Paginator, Pagination
from forgeapi.pagination.cursor import CursorPaginator, CursorPagination, _encode_cursor, _decode_cursor
from forgeapi.pagination.response import (
    PaginatedResponse, CursorResponse,
    PaginationMeta, PaginationLinks, CursorMeta,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_pagination_app() -> FastAPI:
    app = FastAPI()

    @app.get("/items")
    async def list_items(pagination: Pagination):
        return {
            "page": pagination.page,
            "limit": pagination.per_page,
            "offset": pagination.offset,
        }

    return app


def make_cursor_app() -> FastAPI:
    app = FastAPI()

    @app.get("/items")
    async def list_items(p: CursorPagination):
        return {
            "per_page": p.per_page,
            "cursor": p._cursor,
        }

    return app


# ---------------------------------------------------------------------------
# Unit — Paginator defaults
# ---------------------------------------------------------------------------

class TestPaginatorDefaults:
    def test_default_limit(self):
        p = Paginator(page=1, per_page=None, limit=None)
        assert p.per_page == Paginator.DEFAULT_LIMIT

    def test_default_page(self):
        p = Paginator(page=1, per_page=None, limit=None)
        assert p.page == 1

    def test_default_offset(self):
        p = Paginator(page=1, per_page=None, limit=None)
        assert p.offset == 0

    def test_backward_compat_limit_alias(self):
        p = Paginator(page=1, per_page=None, limit=10)
        assert p.per_page == 10
        assert p.limit == 10  # alias still works


class TestPaginatorCalculations:
    def test_offset_page_2(self):
        p = Paginator(page=2, per_page=10, limit=None)
        assert p.offset == 10

    def test_offset_page_3(self):
        p = Paginator(page=3, per_page=5, limit=None)
        assert p.offset == 10

    def test_limit_clamped_to_max(self):
        p = Paginator(page=1, per_page=999, limit=None)
        assert p.per_page == Paginator.MAX_LIMIT

    def test_per_page_takes_precedence_over_limit(self):
        p = Paginator(page=1, per_page=15, limit=5)
        assert p.per_page == 15

    def test_none_per_page_uses_default(self):
        p = Paginator(page=1, per_page=None, limit=None)
        assert p.per_page == Paginator.DEFAULT_LIMIT


class TestPaginatorConfigure:
    def test_configure_default_limit(self):
        Paginator.configure(default_limit=10, max_limit=100)
        p = Paginator(page=1, per_page=None, limit=None)
        assert p.per_page == 10

    def test_configure_max_limit(self):
        Paginator.configure(default_limit=20, max_limit=50)
        p = Paginator(page=1, per_page=999, limit=None)
        assert p.per_page == 50

    def test_configure_invalid_default_raises(self):
        with pytest.raises(ValueError):
            Paginator.configure(default_limit=0, max_limit=100)

    def test_configure_invalid_max_raises(self):
        with pytest.raises(ValueError):
            Paginator.configure(default_limit=10, max_limit=0)

    def test_configure_negative_raises(self):
        with pytest.raises(ValueError):
            Paginator.configure(default_limit=-1, max_limit=100)

    def test_configure_default_exceeds_max_raises(self):
        with pytest.raises(ValueError, match="must not exceed"):
            Paginator.configure(default_limit=200, max_limit=100)


# ---------------------------------------------------------------------------
# Unit — PaginatedResponse structure
# ---------------------------------------------------------------------------

class TestPaginatedResponse:
    def test_fields_present(self):
        meta = PaginationMeta(
            current_page=1, per_page=20, total=100, last_page=5,
            **{"from": 1, "to": 20},
        )
        links = PaginationLinks(prev=None, next="/items?page=2&per_page=20")
        resp = PaginatedResponse(data=["a", "b"], meta=meta, links=links)

        assert resp.meta.current_page == 1
        assert resp.meta.total == 100
        assert resp.meta.last_page == 5
        assert resp.meta.from_item == 1
        assert resp.meta.to_item == 20
        assert resp.links.next == "/items?page=2&per_page=20"
        assert resp.links.prev is None
        assert resp.data == ["a", "b"]

    def test_last_page_ceil(self):
        # 21 total, 20 per page → last_page = 2
        meta = PaginationMeta(
            current_page=1, per_page=20, total=21, last_page=2,
            **{"from": 1, "to": 20},
        )
        assert meta.last_page == 2

    def test_json_alias_from(self):
        meta = PaginationMeta(
            current_page=1, per_page=20, total=5, last_page=1,
            **{"from": 1, "to": 5},
        )
        dumped = meta.model_dump(by_alias=True)
        assert "from" in dumped
        assert "to" in dumped


# ---------------------------------------------------------------------------
# Unit — CursorPaginator encode/decode
# ---------------------------------------------------------------------------

class TestCursorEncoding:
    def test_encode_decode_roundtrip(self):
        payload = {"id": 42}
        assert _decode_cursor(_encode_cursor(payload)) == payload

    def test_decode_invalid_returns_empty(self):
        assert _decode_cursor("!!!not-base64!!!") == {}

    def test_encode_is_url_safe(self):
        cursor = _encode_cursor({"id": 999})
        assert "+" not in cursor
        assert "/" not in cursor


class TestCursorPaginator:
    def test_no_cursor_default_per_page(self):
        p = CursorPaginator(cursor=None, per_page=None)
        assert p.per_page == CursorPaginator.DEFAULT_LIMIT
        assert p._cursor is None
        assert p._cursor_payload == {}

    def test_cursor_decoded_on_init(self):
        cursor = _encode_cursor({"id": 15})
        p = CursorPaginator(cursor=cursor, per_page=None)
        assert p._cursor_payload == {"id": 15}

    def test_per_page_clamped(self):
        p = CursorPaginator(cursor=None, per_page=9999)
        assert p.per_page == CursorPaginator.MAX_LIMIT

    def test_configure(self):
        CursorPaginator.configure(default_limit=10, max_limit=50)
        p = CursorPaginator(cursor=None, per_page=None)
        assert p.per_page == 10
        CursorPaginator.configure(default_limit=20, max_limit=100)


# ---------------------------------------------------------------------------
# Unit — CursorResponse structure
# ---------------------------------------------------------------------------

class TestCursorResponse:
    def test_fields_present(self):
        cursor = _encode_cursor({"id": 20})
        meta = CursorMeta(per_page=20, next_cursor=cursor, prev_cursor=None)
        links = PaginationLinks(prev=None, next=f"/items?cursor={cursor}&per_page=20")
        resp = CursorResponse(data=[1, 2, 3], meta=meta, links=links)

        assert resp.meta.per_page == 20
        assert resp.meta.next_cursor == cursor
        assert resp.meta.prev_cursor is None
        assert resp.links.next is not None
        assert resp.links.prev is None

    def test_no_next_when_last_page(self):
        meta = CursorMeta(per_page=20, next_cursor=None, prev_cursor=None)
        resp = CursorResponse(data=[], meta=meta, links=PaginationLinks())
        assert resp.meta.next_cursor is None


# ---------------------------------------------------------------------------
# Integration — HTTP via ASGI
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_pagination_defaults():
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=make_pagination_app()), base_url="http://test"
    ) as client:
        resp = await client.get("/items")
    assert resp.status_code == 200
    data = resp.json()
    assert data["page"] == 1
    assert data["limit"] == 20
    assert data["offset"] == 0


@pytest.mark.anyio
async def test_pagination_custom_page_and_per_page():
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=make_pagination_app()), base_url="http://test"
    ) as client:
        resp = await client.get("/items?page=3&per_page=10")
    assert resp.status_code == 200
    data = resp.json()
    assert data["page"] == 3
    assert data["limit"] == 10
    assert data["offset"] == 20


@pytest.mark.anyio
async def test_pagination_limit_clamped():
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=make_pagination_app()), base_url="http://test"
    ) as client:
        resp = await client.get("/items?per_page=9999")
    assert resp.status_code == 200
    assert resp.json()["limit"] == 100


@pytest.mark.anyio
async def test_pagination_page_zero_rejected():
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=make_pagination_app()), base_url="http://test"
    ) as client:
        resp = await client.get("/items?page=0")
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_pagination_negative_per_page_rejected():
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=make_pagination_app()), base_url="http://test"
    ) as client:
        resp = await client.get("/items?per_page=-1")
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_pagination_page_too_large_rejected():
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=make_pagination_app()), base_url="http://test"
    ) as client:
        resp = await client.get("/items?page=10001")
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_cursor_app_no_cursor():
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=make_cursor_app()), base_url="http://test"
    ) as client:
        resp = await client.get("/items")
    assert resp.status_code == 200
    data = resp.json()
    assert data["cursor"] is None
    assert data["per_page"] == CursorPaginator.DEFAULT_LIMIT


@pytest.mark.anyio
async def test_cursor_app_with_cursor():
    cursor = _encode_cursor({"id": 50})
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=make_cursor_app()), base_url="http://test"
    ) as client:
        resp = await client.get(f"/items?cursor={cursor}&per_page=10")
    assert resp.status_code == 200
    data = resp.json()
    assert data["cursor"] == cursor
    assert data["per_page"] == 10
