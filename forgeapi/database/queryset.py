from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from tortoise.manager import Manager
from tortoise.queryset import QuerySet

if TYPE_CHECKING:
    from starlette.requests import Request


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
