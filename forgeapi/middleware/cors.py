from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware as _CORSMiddleware


def add_cors(
    app: FastAPI,
    origins: list[str] | None = None,
    allow_credentials: bool = False,
    allow_methods: list[str] | None = None,
    allow_headers: list[str] | None = None,
) -> None:
    """Add CORS middleware to *app*.

    Args:
        app: The FastAPI application instance.
        origins: Allowed origins.  Defaults to ``["*"]`` (all origins).
            When ``allow_credentials=True`` you **must** provide an explicit
            list — combining wildcard origins with credentials is forbidden
            by the CORS specification and raises :exc:`ValueError`.
        allow_credentials: Whether to allow cookies / auth headers in
            cross-origin requests.  Defaults to ``False``.  Must be paired
            with an explicit *origins* list when ``True``.
        allow_methods: Allowed HTTP methods.  Defaults to ``["*"]``.
        allow_headers: Allowed request headers.  Defaults to ``["*"]``.

    Raises:
        ValueError: If ``allow_credentials=True`` is combined with wildcard
            origins (``["*"]`` or the default ``None``).

    Example — open CORS (no credentials)::

        add_cors(app)

    Example — restricted CORS with credentials::

        add_cors(
            app,
            origins=["https://app.example.com"],
            allow_credentials=True,
        )
    """
    resolved_origins: list[str] = origins if origins is not None else ["*"]
    resolved_methods: list[str] = allow_methods if allow_methods is not None else ["*"]
    resolved_headers: list[str] = allow_headers if allow_headers is not None else ["*"]

    if allow_credentials and "*" in resolved_origins:
        raise ValueError(
            "allow_credentials=True is incompatible with wildcard origins ('*'). "
            "Provide an explicit list of allowed origins instead, e.g. "
            "origins=['https://example.com']."
        )

    app.add_middleware(
        _CORSMiddleware,
        allow_origins=resolved_origins,
        allow_credentials=allow_credentials,
        allow_methods=resolved_methods,
        allow_headers=resolved_headers,
    )
