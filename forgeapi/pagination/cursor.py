import base64
import json
from typing import Annotated, Any, ClassVar, Optional, TYPE_CHECKING

from fastapi import Depends, Query

if TYPE_CHECKING:
    from starlette.requests import Request


def _encode_cursor(payload: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode()


def _decode_cursor(cursor: str) -> dict:
    try:
        return json.loads(base64.urlsafe_b64decode(cursor.encode()))
    except Exception:
        return {}


class CursorPaginator:
    """Cursor-based pagination — no OFFSET, stable on inserts/deletes.

    Uses a base64-encoded cursor that encodes the last-seen value of
    ``order_by`` column (default: ``id``).  Each page fetches
    ``per_page + 1`` rows: the extra row signals that a next page exists
    and its value becomes the ``next_cursor``.

    Inject via the :data:`CursorPagination` type alias::

        @route.get("/")
        async def index(self, p: CursorPagination, request: Request):
            return await p.paginate(Post.all(), PostSchema, request)

    Query params:
        ``?cursor=<token>`` — opaque cursor from a previous response.
        ``?per_page=20``    — items per page (default :attr:`DEFAULT_LIMIT`).
    """

    DEFAULT_LIMIT: ClassVar[int] = 20
    MAX_LIMIT: ClassVar[int] = 100

    def __init__(
        self,
        cursor: Optional[str] = Query(None, description="Opaque cursor from previous page"),
        per_page: Optional[int] = Query(None, ge=1, description="Items per page"),
    ) -> None:
        resolved = per_page if per_page is not None else self.DEFAULT_LIMIT
        self.per_page = min(resolved, self.MAX_LIMIT)
        self._cursor = cursor
        self._cursor_payload: dict = _decode_cursor(cursor) if cursor else {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def paginate(
        self,
        queryset: Any,
        schema: type,
        request: "Request | None" = None,
        *,
        order_by: str = "id",
    ):
        """Execute *queryset* and return a :class:`~forgeapi.pagination.response.CursorResponse`.

        Args:
            queryset: A Tortoise queryset (not yet awaited, not yet ordered/filtered).
            schema:   Pydantic schema class used to serialise each row.
            request:  Starlette ``Request`` used to build ``next`` / ``prev`` links.
            order_by: Column name used for cursor comparison.  Must be unique and
                      monotonic (e.g. ``"id"``, ``"-created_at"``).  A leading
                      ``"-"`` means descending.

        Returns:
            :class:`~forgeapi.pagination.response.CursorResponse`
        """
        from .response import CursorResponse, CursorMeta, PaginationLinks

        descending = order_by.startswith("-")
        column = order_by.lstrip("-")
        qs = queryset.order_by(order_by)

        prev_cursor_value = self._cursor_payload.get(column)

        if prev_cursor_value is not None:
            # Filter rows *after* the cursor
            if descending:
                qs = qs.filter(**{f"{column}__lt": prev_cursor_value})
            else:
                qs = qs.filter(**{f"{column}__gt": prev_cursor_value})

        # Fetch one extra to detect if next page exists
        rows = await qs.limit(self.per_page + 1)

        has_next = len(rows) > self.per_page
        if has_next:
            rows = rows[: self.per_page]

        next_cursor = (
            _encode_cursor({column: getattr(rows[-1], column)}) if has_next and rows else None
        )
        # prev_cursor is the cursor the caller used to reach this page
        prev_cursor = self._cursor if self._cursor else None

        next_url = self._build_url(request, next_cursor) if next_cursor else None
        prev_url = self._build_url(request, prev_cursor) if prev_cursor else None

        data = [schema.model_validate(row) for row in rows]

        return CursorResponse(
            data=data,
            meta=CursorMeta(
                per_page=self.per_page,
                next_cursor=next_cursor,
                prev_cursor=prev_cursor,
            ),
            links=PaginationLinks(prev=prev_url, next=next_url),
        )

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    @classmethod
    def configure(cls, default_limit: int = 20, max_limit: int = 100) -> None:
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

    def _build_url(self, request: "Request | None", cursor: str | None) -> str | None:
        if request is None or cursor is None:
            return None
        base = str(request.url).split("?")[0]
        params = {k: v for k, v in request.query_params.items() if k != "cursor"}
        params["cursor"] = cursor
        params["per_page"] = str(self.per_page)
        return base + "?" + "&".join(f"{k}={v}" for k, v in params.items())


CursorPagination = Annotated[CursorPaginator, Depends()]
