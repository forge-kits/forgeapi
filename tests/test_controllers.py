import pytest
import httpx
from fastapi import FastAPI

from forgeapi.controllers.base import Controller, _pluralize, route


# ---------------------------------------------------------------------------
# _pluralize
# ---------------------------------------------------------------------------

class TestPluralize:
    def test_regular_noun(self):
        assert _pluralize("user") == "users"

    def test_noun_ending_s(self):
        assert _pluralize("users") == "users"

    def test_noun_ending_y(self):
        assert _pluralize("category") == "categories"

    def test_noun_ending_ies(self):
        assert _pluralize("countries") == "countries"

    def test_short_word(self):
        assert _pluralize("tag") == "tags"


# ---------------------------------------------------------------------------
# Auto-prefix generation
# ---------------------------------------------------------------------------

class TestControllerAutoPrefix:
    def test_simple_resource(self):
        class ArticleController(Controller):
            pass
        assert ArticleController.prefix == "/articles"

    def test_namespaced_resource(self):
        class AdminUserController(Controller):
            pass
        assert AdminUserController.prefix == "/admin/users"

    def test_multi_segment_namespace(self):
        # Parts[1:] are joined with "-" to form resource slug: "admin-report" → "admin-reports"
        class SuperAdminReportController(Controller):
            pass
        assert SuperAdminReportController.prefix == "/super/admin-reports"

    def test_explicit_prefix_not_overridden(self):
        class WeirdController(Controller):
            prefix = "/custom-path"
        assert WeirdController.prefix == "/custom-path"

    def test_auto_tags_from_prefix(self):
        class PostController(Controller):
            pass
        assert any("posts" in t for t in PostController.tags)

    def test_explicit_tags_not_overridden(self):
        class NoteController(Controller):
            tags = ["my-notes"]
        assert NoteController.tags == ["my-notes"]


# ---------------------------------------------------------------------------
# @route decorator
# ---------------------------------------------------------------------------

class TestRouteDecorator:
    def test_get(self):
        @route.get("/")
        async def handler():
            pass
        assert handler._route["methods"] == ["GET"]
        assert handler._route["path"] == "/"

    def test_post(self):
        @route.post("/items")
        async def handler():
            pass
        assert handler._route["methods"] == ["POST"]
        assert handler._route["path"] == "/items"

    def test_put(self):
        @route.put("/{id}")
        async def handler():
            pass
        assert handler._route["methods"] == ["PUT"]
        assert handler._route["path"] == "/{id}"

    def test_delete(self):
        @route.delete("/{id}")
        async def handler():
            pass
        assert handler._route["methods"] == ["DELETE"]

    def test_patch(self):
        @route.patch("/{id}")
        async def handler():
            pass
        assert handler._route["methods"] == ["PATCH"]

    def test_explicit_methods(self):
        @route("/multi", methods=["GET", "HEAD"])
        async def handler():
            pass
        assert set(handler._route["methods"]) == {"GET", "HEAD"}

    def test_extra_kwargs_stored(self):
        @route.get("/", summary="List all", deprecated=True)
        async def handler():
            pass
        assert handler._route["kwargs"]["summary"] == "List all"
        assert handler._route["kwargs"]["deprecated"] is True


# ---------------------------------------------------------------------------
# Route registration and HTTP responses
# ---------------------------------------------------------------------------

class TestControllerRouteRegistration:
    def test_multiple_routes_registered(self):
        class GadgetController(Controller):
            @route.get("/")
            async def index(self):
                return []

            @route.post("/")
            async def create(self):
                return {}

        ctrl = GadgetController()
        assert len(ctrl.router.routes) == 2

    @pytest.mark.anyio
    async def test_route_responds_correctly(self):
        class ToolController(Controller):
            @route.get("/")
            async def index(self):
                return {"tools": ["hammer"]}

        app = FastAPI()
        ctrl = ToolController()
        app.include_router(ctrl.router)

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/tools/")
        assert resp.status_code == 200
        assert resp.json() == {"tools": ["hammer"]}

    @pytest.mark.anyio
    async def test_route_with_path_param(self):
        class OrderController(Controller):
            @route.get("/{order_id}")
            async def show(self, order_id: int):
                return {"id": order_id}

        app = FastAPI()
        ctrl = OrderController()
        app.include_router(ctrl.router)

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/orders/42")
        assert resp.status_code == 200
        assert resp.json() == {"id": 42}

    def test_double_init_is_idempotent(self):
        class PinController(Controller):
            @route.get("/")
            async def index(self):
                return []

        PinController()
        PinController()
        assert len(PinController.router.routes) == 1
