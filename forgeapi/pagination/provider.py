from forgeapi.foundation import Provider
from forgeapi.logging import log

_log = log.channel("pagination.provider")


class PaginationProvider(Provider):
    """Configures global pagination limits and registers the request context middleware."""

    def register(self) -> None:
        from .paginator import Paginator
        from forgeapi.middleware.request_context import RequestContextMiddleware

        Paginator.configure(
            default_limit=self.config.pagination.default_limit,
            max_limit=self.config.pagination.max_limit,
        )
        self.app.add_middleware(RequestContextMiddleware)
        _log.debug(
            "Pagination configured: default=%d max=%d",
            Paginator.DEFAULT_LIMIT, Paginator.MAX_LIMIT,
        )
