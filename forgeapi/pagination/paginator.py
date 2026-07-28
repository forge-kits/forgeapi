from typing import ClassVar


class Paginator:
    """Internal pagination config — holds DEFAULT_LIMIT and MAX_LIMIT.

    Set at startup via :meth:`configure` (called by ``PaginationProvider``).
    Read by queryset pagination methods.
    """

    DEFAULT_LIMIT: ClassVar[int] = 20
    MAX_LIMIT: ClassVar[int] = 100

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
