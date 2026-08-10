"""Tests for the @scope query-scope decorator and ForgeQuerySet.__getattr__."""
import pytest
from forgeapi.database.scope import scope
from forgeapi.database.queryset import ForgeQuerySet


# ---------------------------------------------------------------------------
# Minimal fake queryset — bypasses Tortoise.__init__ entirely
# ---------------------------------------------------------------------------

class FakeQS(ForgeQuerySet):
    """Minimal subclass that sets _model without calling Tortoise internals."""

    def __init__(self, model):
        self._model = model

    def filter(self, **kwargs):
        self._last_filter = kwargs
        return self

    def all(self):
        return self


# ---------------------------------------------------------------------------
# Fake model classes
# ---------------------------------------------------------------------------

class BaseModel:
    _scopes: dict = {}

    @classmethod
    def all(cls):
        return FakeQS(cls)


class Post(BaseModel):
    @scope
    def published(qs):
        return qs.filter(is_published=True)

    @scope
    def popular(qs, threshold=100):
        return qs.filter(views__gte=threshold)


class Article(Post):
    """Inherits scopes from Post and adds its own."""

    @scope
    def featured(qs):
        return qs.filter(is_featured=True)


class Override(Post):
    """Overrides Post.published with a different filter."""

    @scope
    def published(qs):
        return qs.filter(status="active")


# ---------------------------------------------------------------------------
# scope descriptor
# ---------------------------------------------------------------------------

class TestScopeDescriptor:
    def test_is_scope_flag(self):
        assert scope(lambda qs: qs)._is_scope is True

    def test_name_preserved(self):
        def my_scope(qs):
            ...

        s = scope(my_scope)
        assert s.__name__ == "my_scope"

    def test_set_name_updates_name(self):
        assert Post.__dict__["published"].__name__ == "published"

    def test_registers_in_owner_scopes(self):
        assert "published" in Post.__dict__["_scopes"]
        assert "popular" in Post.__dict__["_scopes"]

    def test_subclass_gets_own_scopes_dict(self):
        # Article._scopes should be its own dict, not inherited from Post
        assert Post.__dict__.get("_scopes") is not Article.__dict__.get("_scopes")

    def test_class_level_access_returns_callable(self):
        result = Post.published
        assert callable(result)

    def test_class_level_calls_all_then_scope(self):
        qs = Post.published()
        assert isinstance(qs, FakeQS)
        assert qs._last_filter == {"is_published": True}

    def test_class_level_with_args(self):
        qs = Post.popular(threshold=500)
        assert qs._last_filter == {"views__gte": 500}

    def test_class_level_default_arg(self):
        qs = Post.popular()
        assert qs._last_filter == {"views__gte": 100}


# ---------------------------------------------------------------------------
# ForgeQuerySet.__getattr__
# ---------------------------------------------------------------------------

class TestForgeQuerySetGetattr:
    def test_scope_callable_on_queryset(self):
        qs = FakeQS(Post)
        result = qs.published()
        assert result._last_filter == {"is_published": True}

    def test_scope_with_arg_on_queryset(self):
        qs = FakeQS(Post)
        result = qs.popular(threshold=250)
        assert result._last_filter == {"views__gte": 250}

    def test_unknown_attr_raises_attribute_error(self):
        qs = FakeQS(Post)
        with pytest.raises(AttributeError, match="no attribute 'nonexistent'"):
            _ = qs.nonexistent

    def test_private_attr_raises_attribute_error(self):
        qs = FakeQS(Post)
        with pytest.raises(AttributeError):
            _ = qs._private_scope


# ---------------------------------------------------------------------------
# Inheritance
# ---------------------------------------------------------------------------

class TestScopeInheritance:
    def test_inherited_scope_works_on_queryset(self):
        qs = FakeQS(Article)
        result = qs.published()
        assert result._last_filter == {"is_published": True}

    def test_own_scope_works_on_queryset(self):
        qs = FakeQS(Article)
        result = qs.featured()
        assert result._last_filter == {"is_featured": True}

    def test_overridden_scope_uses_child_definition(self):
        qs = FakeQS(Override)
        result = qs.published()
        assert result._last_filter == {"status": "active"}

    def test_parent_scope_not_affected_by_child_override(self):
        qs = FakeQS(Post)
        result = qs.published()
        assert result._last_filter == {"is_published": True}

    def test_class_level_inherited_scope(self):
        qs = Article.published()
        assert qs._last_filter == {"is_published": True}

    def test_class_level_overridden_scope(self):
        qs = Override.published()
        assert qs._last_filter == {"status": "active"}
