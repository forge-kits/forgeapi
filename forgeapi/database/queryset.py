from __future__ import annotations

import asyncio
from typing import Any, TYPE_CHECKING

from tortoise.manager import Manager
from tortoise.queryset import QuerySet

if TYPE_CHECKING:
    from starlette.requests import Request


class ForgeQuerySet(QuerySet):
    async def paginate(self, request: "Request", schema: type | None = None):
        from forgeapi.pagination.response import PaginatedResponse, PaginationMeta, PaginationLinks
        from forgeapi.pagination.paginator import Paginator

        try:
            page = max(1, int(request.query_params.get("page", 1)))
        except (ValueError, TypeError):
            page = 1
        try:
            per_page = min(int(request.query_params.get("per_page", Paginator.DEFAULT_LIMIT)), Paginator.MAX_LIMIT)
        except (ValueError, TypeError):
            per_page = Paginator.DEFAULT_LIMIT
        offset   = (page - 1) * per_page

        total, rows = await asyncio.gather(
            self.count(),
            self.offset(offset).limit(per_page),
        )

        last_page = max(1, -(-total // per_page))

        base   = str(request.url).split("?")[0]
        params = {k: v for k, v in request.query_params.items() if k != "page"}
        params["per_page"] = str(per_page)

        def make_url(p: int) -> str:
            return base + "?" + "&".join(f"{k}={v}" for k, v in {**params, "page": p}.items())

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
            links=PaginationLinks(
                prev=make_url(page - 1) if page > 1 else None,
                next=make_url(page + 1) if page < last_page else None,
            ),
        )


class ForgeManager(Manager):
    def get_queryset(self) -> ForgeQuerySet:
        return ForgeQuerySet(self._model)
