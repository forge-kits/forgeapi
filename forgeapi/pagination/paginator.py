from typing import Annotated, ClassVar, Optional
from fastapi import Depends, Query


class Paginator:
    """Pagination dependency — extracts ``?page`` and ``?limit`` from query params.

    Inject via FastAPI's type annotation syntax.  Reads ``page`` (1-based) and
    ``limit`` from the query string.  ``limit`` is clamped to :attr:`MAX_LIMIT`
    and defaults to :attr:`DEFAULT_LIMIT` when omitted.

    Class Attributes:
        DEFAULT_LIMIT: Items per page when ``?limit`` is not provided.
            Defaults to ``20``.  Override globally with :meth:`configure` or
            via ``Core(pagination=True)``.
        MAX_LIMIT: Hard ceiling on ``?limit`` regardless of what the client
            sends.  Defaults to ``100``.

    Attributes:
        page: Current page number (1-based, from query string).
        limit: Resolved items per page (after clamping to ``MAX_LIMIT``).
        offset: SQL-style row offset ``(page - 1) * limit``.

    Example::

        import asyncio
        from forgeapi.pagination import Paginator

        @router.get("/products")
        async def list_products(pagination: Paginator):
            total, items = await asyncio.gather(
                Product.all().count(),
                Product.all().order_by("-created_at")
                    .offset(pagination.offset)
                    .limit(pagination.limit),
            )
            return {"items": items, "total": total, "page": pagination.page, "limit": pagination.limit}

    Query string usage::

        GET /products?page=2&limit=50
        # pagination.page == 2
        # pagination.limit == 50
        # pagination.offset == 50

    Global configuration::

        Paginator.configure(default_limit=10, max_limit=50)
        # or via Core:
        Core(app, pagination=10)
    """

    DEFAULT_LIMIT: ClassVar[int] = 20
    MAX_LIMIT: ClassVar[int] = 100

    def __init__(
        self,
        page: int = Query(1, ge=1, le=10000, description="Page number (1-based, max 10 000)"),
        limit: Optional[int] = Query(None, ge=1, description="Items per page"),
    ) -> None:
        resolved_limit = limit if limit is not None else self.DEFAULT_LIMIT
        self.limit = min(resolved_limit, self.MAX_LIMIT)
        self.page = page
        self.offset = (page - 1) * self.limit

    @classmethod
    def configure(cls, default_limit: int = 20, max_limit: int = 100) -> None:
        """Update the class-level defaults for all future ``Paginator`` instances.

        Must be called at startup before the application begins serving requests.

        Args:
            default_limit: New default for ``?limit`` when omitted by the client.
            max_limit: New hard ceiling for ``?limit``.

        Raises:
            ValueError: If either value is less than 1, or if
                ``default_limit > max_limit``.

        Example::

            Paginator.configure(default_limit=10, max_limit=50)
        """
        if default_limit < 1 or max_limit < 1:
            raise ValueError("default_limit and max_limit must be >= 1")
        if default_limit > max_limit:
            raise ValueError(
                f"default_limit ({default_limit}) must not exceed max_limit ({max_limit})"
            )
        cls.DEFAULT_LIMIT = default_limit
        cls.MAX_LIMIT = max_limit


Pagination = Annotated[Paginator, Depends()]
