from fastapi import APIRouter


def route(path: str, methods: list[str], **kwargs):
    """Declare a controller method as a route handler.

    Usage::

        class UserController(Controller):
            prefix = "/users"

            @route("/{user_id}", methods=["GET"])
            async def show(self, user_id: int) -> UserSchema:
                ...

            @route("/", methods=["POST"])
            async def create(self, payload: UserCreateSchema):
                ...
    """
    def decorator(func):
        func._route = {"path": path, "methods": [m.upper() for m in methods], "kwargs": kwargs}
        return func
    return decorator


class Controller:
    """Base controller class — auto-registers @route-decorated methods.

    Subclass it, set ``prefix`` and optionally ``tags``, decorate methods
    with ``@route``.  No ``__init__`` boilerplate needed.

    ``prefix`` defaults to the pluralized lowercase class name
    (``UserController`` → ``/users``).
    """

    prefix: str = ""
    tags: list[str] = []

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)

        if "prefix" not in cls.__dict__:
            name = cls.__name__.removesuffix("Controller").lower()
            if name.endswith("y"):
                name = name[:-1] + "ies"
            elif not name.endswith("s"):
                name += "s"
            cls.prefix = f"/{name}"

        if "tags" not in cls.__dict__ or not cls.tags:
            cls.tags = [cls.prefix.lstrip("/")]

        cls.router = APIRouter(prefix=cls.prefix, tags=cls.tags)
        cls._registered = False

    def __init__(self):
        cls = self.__class__
        if cls._registered:
            return
        cls._registered = True
        for name in dir(cls):
            if name.startswith("_"):
                continue
            fn = getattr(cls, name)
            if callable(fn) and hasattr(fn, "_route"):
                meta = fn._route
                cls.router.add_api_route(
                    meta["path"],
                    getattr(self, name),
                    methods=meta["methods"],
                    **meta["kwargs"],
                )
