from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class PaginationMeta(BaseModel):
    current_page: int
    per_page: int
    total: int
    last_page: int
    from_item: int = Field(alias="from")
    to_item: int = Field(alias="to")

    model_config = {"populate_by_name": True}


class PaginationLinks(BaseModel):
    prev: str | None = None
    next: str | None = None


class PaginatedResponse(BaseModel, Generic[T]):
    data: list[T]
    meta: PaginationMeta
    links: PaginationLinks


class CursorMeta(BaseModel):
    per_page: int
    next_cursor: str | None = None
    prev_cursor: str | None = None


class CursorResponse(BaseModel, Generic[T]):
    data: list[T]
    meta: CursorMeta
    links: PaginationLinks
