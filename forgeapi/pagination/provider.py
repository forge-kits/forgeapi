from forgeapi.foundation import Provider
from forgeapi.logging import log

_log = log.channel("pagination.provider")


class PaginationProvider(Provider):
    """Configures the global :class:`~forgeapi.pagination.paginator.Paginator` limits."""

    def register(self) -> None:
        from .paginator import Paginator
        Paginator.configure(
            default_limit=self.config.pagination.default_limit,
            max_limit=self.config.pagination.max_limit,
        )
        _log.debug(
            "Pagination configured: default=%d max=%d",
            Paginator.DEFAULT_LIMIT, Paginator.MAX_LIMIT,
        )
