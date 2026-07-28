from __future__ import annotations

import asyncio
import base64
import json
from typing import Any

from tortoise.manager import Manager
from tortoise.queryset import QuerySet


def _encode_cursor(payload: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode()


def _decode_cursor(cursor: str) -> dict:
    try:
        return json.loads(base64.urlsafe_b64decode(cursor.encode()))
    except Exception:
        return {}


class ForgeQuerySet(QuerySet):

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        model_class = self._model
        for cls in model_class.__mro__:
            scopes = cls.__dict__.get("_scopes", {})
            if name in scopes:
                fn = scopes[name]

                def _caller(*args: Any, _fn: Any = fn, **kwargs: Any) -> Any:
                    return _fn(self, *args, **kwargs)

                _caller.__name__ = name
                return _caller
        raise AttributeError(
            f"'{type(self).__name__}' object has no attribute '{name}'. "
            f"To use '{name}' as a scope, decorate it with @scope on {model_class.__name__}."
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_page_params(self, per_page_arg: int | None) -> tuple[int, int, int]:
        """Return (page, per_page, offset) from request context + explicit arg."""
        from forgeapi.pagination.paginator import Paginator
        from forgeapi.http.context import get_request

        request = get_request()

        if request is not None:
            try:
                page = max(1, int(request.query_params.get("page", 1)))
            except (ValueError, TypeError):
                page = 1
            if per_page_arg is None:
                try:
                    per_page = int(request.query_params.get("per_page", Paginator.DEFAULT_LIMIT))
                except (ValueError, TypeError):
                    per_page = Paginator.DEFAULT_LIMIT
            else:
                per_page = per_page_arg
        else:
            page = 1
            per_page = per_page_arg if per_page_arg is not None else Paginator.DEFAULT_LIMIT

        per_page = min(per_page, Paginator.MAX_LIMIT)
        return page, per_page, (page - 1) * per_page

    def _page_links(self, page: int, per_page: int, last_page: int | None, has_next: bool | None = None):
        """Build (prev_url, next_url) from the current request context."""
        from forgeapi.http.context import get_request
        request = get_request()
        if request is None:
            return None, None

        base = str(request.url).split("?")[0]
        params = {k: v for k, v in request.query_params.items() if k != "page"}
        params["per_page"] = str(per_page)

        def url(p: int) -> str:
            return base + "?" + "&".join(f"{k}={v}" for k, v in {**params, "page": p}.items())

        can_prev = page > 1
        can_next = (page < last_page) if last_page is not None else bool(has_next)
        return url(page - 1) if can_prev else None, url(page + 1) if can_next else None

    # ------------------------------------------------------------------
    # Public pagination API
    # ------------------------------------------------------------------

    async def paginate(self, per_page: int | None = None, schema: type | None = None):
        """Offset pagination with total count — equivalent to Laravel ``paginate()``.

        Runs two queries: ``COUNT`` + ``SELECT … OFFSET … LIMIT``.
        Returns :class:`~forgeapi.pagination.response.PaginatedResponse` with
        full meta (total, last_page, from/to).

        Args:
            per_page: Items per page.  Overrides ``?per_page`` when given.
                      Defaults to ``?per_page`` query param → ``DEFAULT_LIMIT``.
            schema:   Pydantic schema for serialisation.  ``None`` returns raw
                      Tortoise model instances.

        Usage::

            return await Post.all().order_by("-created_at").paginate(15, PostSchema)
        """
        from forgeapi.pagination.response import PaginatedResponse, PaginationMeta, PaginationLinks

        page, per_page, offset = self._resolve_page_params(per_page)
        total, rows = await asyncio.gather(
            self.count(),
            self.offset(offset).limit(per_page),
        )

        last_page = max(1, -(-total // per_page))
        prev_url, next_url = self._page_links(page, per_page, last_page)
        data = [schema.model_validate(row) for row in rows] if schema else list(rows)

        return PaginatedResponse(
            data=data,
            meta=PaginationMeta.model_construct(
                current_page=page,
                per_page=per_page,
                total=total,
                last_page=last_page,
                from_item=offset + 1 if total else 0,
                to_item=min(offset + per_page, total),
            ),
            links=PaginationLinks(prev=prev_url, next=next_url),
        )

    async def simple_paginate(self, per_page: int | None = None, schema: type | None = None):
        """Offset pagination without total count — equivalent to Laravel ``simplePaginate()``.

        Runs a single ``SELECT … OFFSET … LIMIT+1`` query (no ``COUNT``).
        Returns :class:`~forgeapi.pagination.response.SimplePaginatedResponse`
        with only ``prev``/``next`` links — faster on large tables.

        Args:
            per_page: Items per page.  Same resolution as :meth:`paginate`.
            schema:   Pydantic schema for serialisation.

        Usage::

            return await Post.all().order_by("-created_at").simple_paginate(15, PostSchema)
        """
        from forgeapi.pagination.response import SimplePaginatedResponse, SimplePaginationMeta, PaginationLinks

        page, per_page, offset = self._resolve_page_params(per_page)
        rows = await self.offset(offset).limit(per_page + 1)

        has_next = len(rows) > per_page
        if has_next:
            rows = rows[:per_page]

        prev_url, next_url = self._page_links(page, per_page, last_page=None, has_next=has_next)
        data = [schema.model_validate(row) for row in rows] if schema else list(rows)

        return SimplePaginatedResponse(
            data=data,
            meta=SimplePaginationMeta(current_page=page, per_page=per_page),
            links=PaginationLinks(prev=prev_url, next=next_url),
        )

    async def cursor_paginate(
        self,
        per_page: int | None = None,
        schema: type | None = None,
        *,
        order_by: str = "id",
    ):
        """Cursor-based pagination — equivalent to Laravel ``cursorPaginate()``.

        No ``OFFSET``, stable on concurrent inserts/deletes.
        Returns :class:`~forgeapi.pagination.response.CursorResponse`.

        Args:
            per_page: Items per page.  Same resolution as :meth:`paginate`.
            schema:   Pydantic schema for serialisation.
            order_by: Column for cursor comparison.  Prefix with ``"-"`` for
                      descending.  Must be unique and monotonic (e.g. ``"id"``,
                      ``"-created_at"``).

        Usage::

            return await Post.all().cursor_paginate(15, PostSchema, order_by="-created_at")
        """
        from forgeapi.pagination.paginator import Paginator
        from forgeapi.pagination.response import CursorResponse, CursorMeta, PaginationLinks
        from forgeapi.http.context import get_request

        request = get_request()

        if per_page is None:
            if request is not None:
                try:
                    per_page = int(request.query_params.get("per_page", Paginator.DEFAULT_LIMIT))
                except (ValueError, TypeError):
                    per_page = Paginator.DEFAULT_LIMIT
            else:
                per_page = Paginator.DEFAULT_LIMIT
        per_page = min(per_page, Paginator.MAX_LIMIT)

        cursor_str = request.query_params.get("cursor") if request else None
        cursor_payload = _decode_cursor(cursor_str) if cursor_str else {}

        descending = order_by.startswith("-")
        column = order_by.lstrip("-")
        qs = self.order_by(order_by)

        prev_cursor_value = cursor_payload.get(column)
        if prev_cursor_value is not None:
            qs = qs.filter(**{f"{column}__{'lt' if descending else 'gt'}": prev_cursor_value})

        rows = await qs.limit(per_page + 1)
        has_next = len(rows) > per_page
        if has_next:
            rows = rows[:per_page]

        next_cursor = _encode_cursor({column: getattr(rows[-1], column)}) if has_next and rows else None
        prev_cursor = cursor_str or None

        def cursor_url(cur: str | None) -> str | None:
            if request is None or cur is None:
                return None
            base = str(request.url).split("?")[0]
            params = {k: v for k, v in request.query_params.items() if k != "cursor"}
            params["cursor"] = cur
            params["per_page"] = str(per_page)
            return base + "?" + "&".join(f"{k}={v}" for k, v in params.items())

        data = [schema.model_validate(row) for row in rows] if schema else list(rows)

        return CursorResponse(
            data=data,
            meta=CursorMeta(per_page=per_page, next_cursor=next_cursor, prev_cursor=prev_cursor),
            links=PaginationLinks(prev=cursor_url(prev_cursor), next=cursor_url(next_cursor)),
        )


class ForgeManager(Manager):
    def get_queryset(self) -> ForgeQuerySet:
        return ForgeQuerySet(self._model)
