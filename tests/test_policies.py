"""Tests for Policy + Gate."""
import pytest
from fastapi import HTTPException

from forgeapi.policies import Policy, Gate, gate as global_gate


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def fresh_gate() -> Gate:
    return Gate()


class FakeUser:
    def __init__(self, id: int, role: str = "user"):
        self.id = id
        self.role = role


class Post:
    def __init__(self, author_id: int):
        self.author_id = author_id


class Comment:
    def __init__(self, author_id: int):
        self.author_id = author_id


# ---------------------------------------------------------------------------
# Basic allow / deny
# ---------------------------------------------------------------------------

class TestBasicPolicy:
    @pytest.fixture
    def g(self):
        g = fresh_gate()

        class PostPolicy(Policy):
            async def view(self, user, post) -> bool:
                return True

            async def create(self, user) -> bool:
                return user is not None

            async def update(self, user, post) -> bool:
                return post.author_id == user.id

            async def delete(self, user, post) -> bool:
                return post.author_id == user.id

        g.register(Post, PostPolicy)
        return g

    async def test_view_allowed_for_everyone(self, g):
        assert await g.allows(FakeUser(1), "view", Post(author_id=99)) is True

    async def test_create_allowed_when_user_present(self, g):
        assert await g.allows(FakeUser(1), "create", Post) is True

    async def test_update_allowed_for_owner(self, g):
        user = FakeUser(5)
        post = Post(author_id=5)
        assert await g.allows(user, "update", post) is True

    async def test_update_denied_for_non_owner(self, g):
        user = FakeUser(3)
        post = Post(author_id=5)
        assert await g.allows(user, "update", post) is False

    async def test_denies_is_inverse(self, g):
        user = FakeUser(3)
        post = Post(author_id=5)
        assert await g.denies(user, "update", post) is True


# ---------------------------------------------------------------------------
# authorize raises 403
# ---------------------------------------------------------------------------

class TestAuthorize:
    @pytest.fixture
    def g(self):
        g = fresh_gate()

        class PostPolicy(Policy):
            async def update(self, user, post) -> bool:
                return post.author_id == user.id

        g.register(Post, PostPolicy)
        return g

    async def test_authorize_passes_for_owner(self, g):
        user = FakeUser(1)
        post = Post(author_id=1)
        await g.authorize(user, "update", post)  # no exception

    async def test_authorize_raises_403_for_non_owner(self, g):
        with pytest.raises(HTTPException) as exc:
            await g.authorize(FakeUser(2), "update", Post(author_id=1))
        assert exc.value.status_code == 403
        assert exc.value.detail == "This action is unauthorized."


# ---------------------------------------------------------------------------
# before() hook
# ---------------------------------------------------------------------------

class TestBeforeHook:
    @pytest.fixture
    def g(self):
        g = fresh_gate()

        class PostPolicy(Policy):
            async def before(self, user, action):
                if user.role == "admin":
                    return True  # admins bypass everything
                return None

            async def update(self, user, post) -> bool:
                return post.author_id == user.id

        g.register(Post, PostPolicy)
        return g

    async def test_admin_bypasses_ownership_check(self, g):
        admin = FakeUser(id=99, role="admin")
        post = Post(author_id=1)  # different owner
        assert await g.allows(admin, "update", post) is True

    async def test_regular_user_still_checked(self, g):
        user = FakeUser(id=2, role="user")
        post = Post(author_id=1)
        assert await g.allows(user, "update", post) is False

    async def test_before_false_blocks_admin(self, g2=None):
        g = fresh_gate()

        class StrictPolicy(Policy):
            async def before(self, user, action):
                return False  # deny everyone unconditionally

            async def view(self, user, post) -> bool:
                return True  # never reached

        g.register(Post, StrictPolicy)
        assert await g.allows(FakeUser(1), "view", Post(author_id=1)) is False


# ---------------------------------------------------------------------------
# No policy registered
# ---------------------------------------------------------------------------

class TestNoPolicyRegistered:
    async def test_allows_returns_false_when_no_policy(self):
        g = fresh_gate()
        assert await g.allows(FakeUser(1), "view", Post(author_id=1)) is False

    async def test_authorize_raises_403_when_no_policy(self):
        g = fresh_gate()
        with pytest.raises(HTTPException) as exc:
            await g.authorize(FakeUser(1), "view", Post(author_id=1))
        assert exc.value.status_code == 403


# ---------------------------------------------------------------------------
# Missing action method
# ---------------------------------------------------------------------------

class TestMissingMethod:
    async def test_missing_method_denies(self):
        g = fresh_gate()

        class PostPolicy(Policy):
            async def view(self, user, post) -> bool:
                return True
            # no "delete" method

        g.register(Post, PostPolicy)
        assert await g.allows(FakeUser(1), "delete", Post(author_id=1)) is False


# ---------------------------------------------------------------------------
# @gate.policy decorator
# ---------------------------------------------------------------------------

class TestPolicyDecorator:
    async def test_decorator_registers_policy(self):
        g = fresh_gate()

        @g.policy(Comment)
        class CommentPolicy(Policy):
            async def delete(self, user, comment) -> bool:
                return comment.author_id == user.id

        user = FakeUser(7)
        assert await g.allows(user, "delete", Comment(author_id=7)) is True
        assert await g.allows(user, "delete", Comment(author_id=9)) is False

    async def test_decorator_returns_policy_class(self):
        g = fresh_gate()

        @g.policy(Comment)
        class CommentPolicy(Policy):
            async def view(self, user, comment) -> bool:
                return True

        assert CommentPolicy is not None
        assert issubclass(CommentPolicy, Policy)


# ---------------------------------------------------------------------------
# Class-level subject (no instance)
# ---------------------------------------------------------------------------

class TestClassSubject:
    async def test_create_with_class_subject(self):
        g = fresh_gate()

        class PostPolicy(Policy):
            async def create(self, user) -> bool:
                return user.role == "editor"

        g.register(Post, PostPolicy)
        editor = FakeUser(1, role="editor")
        viewer = FakeUser(2, role="user")
        assert await g.allows(editor, "create", Post) is True
        assert await g.allows(viewer, "create", Post) is False
