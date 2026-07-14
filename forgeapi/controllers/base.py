import functools
import inspect
import re

from fastapi import APIRouter


def _pluralize(name: str) -> str:
    if name.endswith("y") and len(name) >= 2 and name[-2] not in "aeiou":
        return name[:-1] + "ies"
    if name.endswith("s"):
        return name
    return name + "s"


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


def _make_endpoint(ctrl_cls, method_name: str):
    """Return a per-request factory so each request gets a fresh controller instance."""
    original_fn = getattr(ctrl_cls, method_name)
    sig = inspect.signature(original_fn)
    # Drop 'self' from the signature so FastAPI doesn't try to inject it
    params = list(sig.parameters.values())[1:]

    @functools.wraps(original_fn)
    async def _endpoint(**kwargs):
        return await getattr(ctrl_cls(), method_name)(**kwargs)

    _endpoint.__signature__ = sig.replace(parameters=params)
    return _endpoint


class Controller:
    """Base controller class — auto-registers @route-decorated methods.

    Subclass it, set ``prefix`` and optionally ``tags``, decorate methods
    with ``@route``.  No ``__init__`` boilerplate needed.

    ``prefix`` defaults based on the class name:
    - ``UserController``      → ``/users``
    - ``AdminUserController`` → ``/admin/users``

    Set ``schema`` to apply a default ``response_model`` to all routes
    that don't specify one explicitly (204 routes are skipped)::

        class PostController(Controller):
            schema = PostResponse
    """

    prefix: str = ""
    tags: list[str] | None = None
    guards: list | None = None
    schema: type | None = None

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

        # Always create fresh lists so subclasses never share the base-class defaults
        if "tags" not in cls.__dict__ or not cls.__dict__.get("tags"):
            cls.tags = [cls.prefix.lstrip("/")]
        else:
            cls.tags = list(cls.__dict__["tags"])

        cls.guards = list(cls.__dict__.get("guards") or [])

        # Wrap guards in Depends if not already wrapped
        from fastapi import Depends
        deps = [g if hasattr(g, "dependency") else Depends(g) for g in cls.guards]

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
                kwargs = dict(meta["kwargs"])
                # inject controller schema as response_model when not set explicitly
                # skip 204 No Content routes — they have no body
                if (
                    cls.schema is not None
                    and "response_model" not in kwargs
                    and kwargs.get("status_code") != 204
                ):
                    kwargs["response_model"] = cls.schema
                cls.router.add_api_route(
                    meta["path"],
                    _make_endpoint(cls, name),
                    methods=meta["methods"],
                    **kwargs,
                )
