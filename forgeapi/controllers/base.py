import re

from fastapi import APIRouter


def _pluralize(name: str) -> str:
    if name.endswith("y"):
        return name[:-1] + "ies"
    if not name.endswith("s"):
        return name + "s"
    return name


class _Route:
    """Declare a controller method as a route handler.

    Supports both explicit and shorthand forms::

        @route("/", methods=["GET"])   # explicit — still works
        @route.get("/")
        @route.post("/")
        @route.put("/{id}")
        @route.delete("/{id}")
        @route.patch("/{id}")
    """

    def __call__(self, path: str, methods: list[str], **kwargs):
        def decorator(func):
            func._route = {"path": path, "methods": [m.upper() for m in methods], "kwargs": kwargs}
            return func
        return decorator

    def get(self, path: str, **kwargs):    return self(path, ["GET"], **kwargs)
    def post(self, path: str, **kwargs):   return self(path, ["POST"], **kwargs)
    def put(self, path: str, **kwargs):    return self(path, ["PUT"], **kwargs)
    def delete(self, path: str, **kwargs): return self(path, ["DELETE"], **kwargs)
    def patch(self, path: str, **kwargs):  return self(path, ["PATCH"], **kwargs)


route = _Route()


class Controller:
    """Base controller class — auto-registers @route-decorated methods.

    Subclass it, set ``prefix`` and optionally ``tags``, decorate methods
    with ``@route``.  No ``__init__`` boilerplate needed.

    ``prefix`` defaults based on the class name:
    - ``UserController``      → ``/users``
    - ``AdminUserController`` → ``/admin/users``
    """

    prefix: str = ""
    tags: list[str] = []
    guards: list = []

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)

        if "prefix" not in cls.__dict__:
            raw = cls.__name__.removesuffix("Controller")
            parts = re.findall(r'[A-Z][a-z0-9]*', raw)
            if len(parts) >= 2:
                namespace = parts[0].lower()
                resource_slug = "-".join(p.lower() for p in parts[1:])
                cls.prefix = f"/{namespace}/{_pluralize(resource_slug)}"
            else:
                name = parts[0].lower() if parts else raw.lower()
                cls.prefix = f"/{_pluralize(name)}"

        if "tags" not in cls.__dict__ or not cls.tags:
            cls.tags = [cls.prefix.lstrip("/")]

        # Wrap guards in Depends if not already wrapped
        from fastapi import Depends
        raw_guards = list(cls.__dict__.get("guards") or [])
        deps = [g if hasattr(g, "dependency") else Depends(g) for g in raw_guards]

        cls.router = APIRouter(prefix=cls.prefix, tags=cls.tags, dependencies=deps or None)
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
