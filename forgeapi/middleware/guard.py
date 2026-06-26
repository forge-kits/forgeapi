import inspect


class Guard:
    """Base class for DI-based per-route / per-controller middleware.

    Subclass and override :meth:`handle`. FastAPI injects parameters declared
    in ``handle`` automatically — the same way as a regular route handler.

    ``__call__`` is kept as the FastAPI-facing entry point; its signature is
    patched at class creation time to mirror ``handle``, so the dependency
    injection system sees the correct parameters.

    Example — block by header::

        from forgeapi.middleware import Guard
        from fastapi import HTTPException, Request

        class ApiKeyGuard(Guard):
            def __init__(self, header: str = "X-API-Key"):
                self.header = header

            async def handle(self, request: Request) -> None:
                if not request.headers.get(self.header):
                    raise HTTPException(403, "Missing API key")

    Example — inject FastAPI dependencies::

        from forgeapi.auth import CurrentUser

        class ActiveUserGuard(Guard):
            async def handle(self, user: CurrentUser) -> None:
                if not user.is_active:
                    raise HTTPException(403, "Account disabled")

    Per-route usage::

        @route.delete("/{id}", dependencies=[Depends(ApiKeyGuard())])
        async def destroy(self, id: int): ...

    Per-controller usage (applies to every route)::

        class AdminController(Controller):
            guards = [ActiveUserGuard()]
    """

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        if "handle" in cls.__dict__:
            handle_fn = cls.__dict__["handle"]

            async def __call__(self, **kw: object) -> None:
                return await self.handle(**kw)

            # Mirror handle's signature onto __call__ so FastAPI can inspect
            # it and inject the correct dependencies (e.g. CurrentUser, Request).
            __call__.__signature__ = inspect.signature(handle_fn)
            cls.__call__ = __call__

    async def handle(self) -> None:
        pass
