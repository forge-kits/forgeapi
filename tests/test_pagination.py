import pytest
import httpx
from fastapi import FastAPI

from forgeapi.pagination.paginator import Paginator, Pagination


# ---------------------------------------------------------------------------
# TestClient app
# ---------------------------------------------------------------------------

app = FastAPI()


@app.get("/items")
async def list_items(pagination: Pagination):
    return {
        "page": pagination.page,
        "limit": pagination.limit,
        "offset": pagination.offset,
    }


# ---------------------------------------------------------------------------
# Unit tests for Paginator (synchronous)
# ---------------------------------------------------------------------------

class TestPaginatorDefaults:
    def test_default_limit(self):
        # Paginator uses FastAPI Query defaults — must pass explicit values when calling directly
        p = Paginator(page=1, limit=None)
        assert p.limit == Paginator.DEFAULT_LIMIT

    def test_default_page(self):
        p = Paginator(page=1, limit=None)
        assert p.page == 1

    def test_default_offset(self):
        p = Paginator(page=1, limit=None)
        assert p.offset == 0


class TestPaginatorCalculations:
    def test_offset_page_2(self):
        p = Paginator(page=2, limit=10)
        assert p.offset == 10

    def test_offset_page_3(self):
        p = Paginator(page=3, limit=5)
        assert p.offset == 10

    def test_limit_clamped_to_max(self):
        p = Paginator(page=1, limit=999)
        assert p.limit == Paginator.MAX_LIMIT

    def test_limit_at_max(self):
        p = Paginator(page=1, limit=Paginator.MAX_LIMIT)
        assert p.limit == Paginator.MAX_LIMIT

    def test_limit_below_max(self):
        p = Paginator(page=1, limit=5)
        assert p.limit == 5

    def test_none_limit_uses_default(self):
        p = Paginator(page=1, limit=None)
        assert p.limit == Paginator.DEFAULT_LIMIT


class TestPaginatorConfigure:
    def test_configure_default_limit(self):
        Paginator.configure(default_limit=10, max_limit=100)
        p = Paginator(page=1, limit=None)
        assert p.limit == 10

    def test_configure_max_limit(self):
        Paginator.configure(default_limit=20, max_limit=50)
        p = Paginator(page=1, limit=999)
        assert p.limit == 50

    def test_configure_invalid_default_raises(self):
        with pytest.raises(ValueError):
            Paginator.configure(default_limit=0, max_limit=100)

    def test_configure_invalid_max_raises(self):
        with pytest.raises(ValueError):
            Paginator.configure(default_limit=10, max_limit=0)

    def test_configure_negative_raises(self):
        with pytest.raises(ValueError):
            Paginator.configure(default_limit=-1, max_limit=100)


# ---------------------------------------------------------------------------
# Integration via async httpx
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_pagination_defaults():
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/items")
    assert resp.status_code == 200
    data = resp.json()
    assert data["page"] == 1
    assert data["limit"] == 20
    assert data["offset"] == 0


@pytest.mark.anyio
async def test_pagination_custom_page_and_limit():
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/items?page=3&limit=10")
    assert resp.status_code == 200
    data = resp.json()
    assert data["page"] == 3
    assert data["limit"] == 10
    assert data["offset"] == 20


@pytest.mark.anyio
async def test_pagination_limit_clamped():
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/items?limit=9999")
    assert resp.status_code == 200
    assert resp.json()["limit"] == 100


@pytest.mark.anyio
async def test_pagination_page_zero_rejected():
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/items?page=0")
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_pagination_negative_limit_rejected():
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/items?limit=-1")
    assert resp.status_code == 422
