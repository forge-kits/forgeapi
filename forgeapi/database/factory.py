from __future__ import annotations

import functools
import inspect
from typing import Any, ClassVar, Generic, Optional, TypeVar

from forgeapi.exceptions import ForgeAPIConfigError

M = TypeVar("M")


def _load_faker(locale: str):
    try:
        from faker import Faker
    except ImportError:
        raise ForgeAPIConfigError(
            "Factories need the faker package.",
            hint="pip install forge-kits[dev]",
        ) from None
    return Faker(locale)


class _Fake:
    """``faker`` loaded on first use, so the package works without it until a factory runs."""

    def __init__(self) -> None:
        self._faker: dict[str, Any] = {}
        self.locale = "en_US"

    def __getattr__(self, name: str):
        if name.startswith("__"):
            raise AttributeError(name)
        if self.locale not in self._faker:
            self._faker[self.locale] = _load_faker(self.locale)
        return getattr(self._faker[self.locale], name)


#: shared Faker: ``fake.email()``, ``fake.name()``... use it in ``definition()``
fake = _Fake()


class _builder:
    """A method that works on the class (``UserFactory.create()``) and on a built-up factory."""

    def __init__(self, fn):
        self._fn = fn
        functools.update_wrapper(self, fn)

    def __get__(self, obj, owner):
        return functools.partial(self._fn, obj if obj is not None else owner())


class Factory(Generic[M]):
    """Builds model instances from the values ``definition()`` returns.

    ::

        class UserFactory(Factory[User]):
            model = User

            def definition(self):
                return {"name": fake.name(), "email": fake.unique.email()}

            def admin(self):
                return self.state(role="admin")

        user = await UserFactory.create()
        admins = await UserFactory.admin().count(3).create()
        data = await UserFactory.make(name="Ann")      # a dict, nothing is saved

    A relation is another factory used as a value, it is created together with the record::

        def definition(self):
            return {"author": UserFactory(), "title": fake.sentence()}

    Values passed to ``state()``, ``make()`` and ``create()`` win over ``definition()``.
    """

    model: ClassVar[type]

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        # a state method (``def admin(self)``) is callable on the class too: ``UserFactory.admin()``
        for name, attr in list(cls.__dict__.items()):
            if name != "definition" and not name.startswith("_") and inspect.isfunction(attr):
                setattr(cls, name, _builder(attr))

    def __init__(self) -> None:
        self._states: dict[str, Any] = {}
        self._count: Optional[int] = None

    def definition(self) -> dict[str, Any]:
        """The values of a new record. Override in a subclass."""
        return {}

    # -- builder ---------------------------------------------------------

    @_builder
    def state(self, **attrs: Any) -> "Factory[M]":
        """A copy of the factory that always sets ``attrs``."""
        clone = self._clone()
        clone._states.update(attrs)
        return clone

    @_builder
    def count(self, n: int) -> "Factory[M]":
        """A copy of the factory whose ``create()`` and ``make()`` return ``n`` items."""
        clone = self._clone()
        clone._count = n
        return clone

    def _clone(self) -> "Factory[M]":
        clone = type(self)()
        clone._states = dict(self._states)
        clone._count = self._count
        return clone

    # -- building --------------------------------------------------------

    @_builder
    async def make(self, **attrs: Any) -> Any:
        """The values of a record as a dict (or a list of dicts after ``count``). Nothing is saved."""
        if self._count is None:
            return await self._values(attrs, save=False)
        return [await self._values(attrs, save=False) for _ in range(self._count)]

    @_builder
    async def create(self, **attrs: Any) -> Any:
        """Save a record (or a list of them after ``count``) and return it."""
        if self._count is None:
            return await self._create_one(attrs)
        return [await self._create_one(attrs) for _ in range(self._count)]

    async def _create_one(self, attrs: dict[str, Any]) -> M:
        return await self._model().create(**await self._values(attrs, save=True))

    def _model(self) -> type:
        model = getattr(type(self), "model", None)
        if model is None:
            raise ForgeAPIConfigError(
                f"{type(self).__name__} has no model.",
                hint=f"set model = YourModel on {type(self).__name__}",
            )
        return model

    async def _values(self, attrs: dict[str, Any], *, save: bool) -> dict[str, Any]:
        values = {**self.definition(), **self._states, **attrs}
        for name, value in values.items():
            if isinstance(value, Factory):
                values[name] = await value.create() if save else await value.make()
        return values
