import asyncio
from typing import Annotated, Any, ClassVar, Optional, TYPE_CHECKING

from fastapi import Depends, Query

if TYPE_CHECKING:
    from starlette.requests import Request


class Paginator:
    """Offset-based pagination dependency — inject via ``Pagination`` type alias.

    Reads ``?page`` and ``?per_page`` from the query string.
    ``per_page`` is clamped to :attr:`MAX_LIMIT` and defaults to
    :attr:`DEFAULT_LIMIT` when omitted.

    Call :meth:`paginate` to execute the query and get a ready
    :class:`~forgeapi.pagination.response.PaginatedResponse`::

        @route.get("/")
        async def index(self, p: Pagination, request: Request):
            return await p.paginate(Post.all().order_by("-created_at"), PostSchema, request)
    """

    DEFAULT_LIMIT: ClassVar[int] = 20
    MAX_LIMIT: ClassVar[int] = 100

    def __init__(
        self,
        page: int = Query(1, ge=1, le=10_000, description="Page number (1-based)"),
        per_page: Optional[int] = Query(None, ge=1, alias="per_page", description="Items per page"),
        # legacy alias kept for backward compat — per_page takes precedence
        limit: Optional[int] = Query(None, ge=1, include_in_schema=False),
    ) -> None:
        resolved = per_page if per_page is not None else (limit if limit is not None else self.DEFAULT_LIMIT)
        self.per_page = min(resolved, self.MAX_LIMIT)
        self.page = page
        self._offset = (page - 1) * self.per_page

        # backward compat aliases
        self.limit = self.per_page
        self.offset = self._offset

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def paginate(
        self,
        queryset: Any,
        schema: type,
        request: "Request | None" = None,
    ):
        """Execute *queryset* and return a :class:`~forgeapi.pagination.response.PaginatedResponse`.

        Args:
            queryset: A Tortoise queryset (not yet awaited).
            schema:   Pydantic schema class used to serialise each row.
            request:  FastAPI / Starlette ``Request`` — used to build
                      ``prev`` / ``next`` links.  Pass ``None`` to omit links.

        Returns:
            :class:`~forgeapi.pagination.response.PaginatedResponse`
        """
        from .response import PaginatedResponse, PaginationMeta, PaginationLinks

        total, rows = await asyncio.gather(
            queryset.count(),
            queryset.offset(self._offset).limit(self.per_page),
        )

        last_page = max(1, -(-total // self.per_page))  # ceil division
        from_item = self._offset + 1 if total else 0
        to_item = min(self._offset + self.per_page, total)

        prev_url, next_url = self._build_links(request, last_page)

        data = [schema.model_validate(row) for row in rows]

        return PaginatedResponse(
            data=data,
            meta=PaginationMeta.model_construct(
                current_page=self.page,
                per_page=self.per_page,
                total=total,
                last_page=last_page,
                from_item=from_item,
                to_item=to_item,
            ),
            links=PaginationLinks(prev=prev_url, next=next_url),
        )

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    @classmethod
    def configure(cls, default_limit: int = 20, max_limit: int = 100) -> None:
        """Set class-wide defaults.  Call at startup before serving requests.

        Args:
            default_limit: Default ``per_page`` when ``?per_page`` is omitted.
            max_limit:     Hard ceiling on ``?per_page``.

        Raises:
            ValueError: If values are invalid.
        """
        if default_limit < 1 or max_limit < 1:
            raise ValueError("default_limit and max_limit must be >= 1")
        if default_limit > max_limit:
            raise ValueError(
                f"default_limit ({default_limit}) must not exceed max_limit ({max_limit})"
            )
        cls.DEFAULT_LIMIT = default_limit
        cls.MAX_LIMIT = max_limit

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _build_links(self, request: "Request | None", last_page: int) -> tuple[str | None, str | None]:
        if request is None:
            return None, None

        base = str(request.url).split("?")[0]
        params = dict(request.query_params)
        params.pop("page", None)
        params["per_page"] = str(self.per_page)

        def url(p: int) -> str:
            return base + "?" + "&".join(f"{k}={v}" for k, v in {**params, "page": p}.items())

        prev_url = url(self.page - 1) if self.page > 1 else None
        next_url = url(self.page + 1) if self.page < last_page else None
        return prev_url, next_url


Pagination = Annotated[Paginator, Depends()]
