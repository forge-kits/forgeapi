from __future__ import annotations

from typing import Any, Callable


class scope:
    """Decorator — marks a function as a query scope on a ModelMixin subclass.

    Scopes are callable both on the model class (returns a fresh queryset)
    and on any queryset (for chaining)::

        class Post(ModelMixin, Model):
            is_published = fields.BooleanField(default=False)
            views        = fields.IntField(default=0)

            @scope
            def published(qs):
                return qs.filter(is_published=True)

            @scope
            def popular(qs, threshold=100):
                return qs.filter(views__gte=threshold)

        # Class-level — starts a fresh queryset:
        posts = await Post.published()

        # Chained on an existing queryset:
        posts = await Post.filter(author_id=user_id).published().popular(threshold=500)

    Scopes are inherited — a subclass can override a parent scope by
    defining one with the same name.
    """

    _is_scope = True

    def __init__(self, fn: Callable) -> None:
        self._fn = fn
        self.__name__: str = fn.__name__
        self.__doc__ = fn.__doc__

    def __set_name__(self, owner: type, name: str) -> None:
        self.__name__ = name
        if "_scopes" not in owner.__dict__:
            owner._scopes: dict[str, Callable] = {}
        owner._scopes[name] = self._fn

    def __get__(self, obj: Any, objtype: type | None = None) -> Any:
        if objtype is None:
            objtype = type(obj)
        if obj is None:
            # Class-level: Post.published() → Post.all().published()
            fn = self._fn
            name = self.__name__

            def _class_scope(*args: Any, **kwargs: Any) -> Any:
                return fn(objtype.all(), *args, **kwargs)

            _class_scope.__name__ = name
            return _class_scope
        return self._fn
