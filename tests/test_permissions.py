from forgeapi.permissions.models import Role
from tests.conftest import UserModel


# ── Roles ─────────────────────────────────────────────────────────────────────

async def test_assign_and_has_role(user, db):
    await user.assign_role("admin")
    assert await user.has_role("admin") is True


async def test_has_role_false(user, db):
    assert await user.has_role("admin") is False


async def test_has_any_role(user, db):
    await user.assign_role("editor")
    assert await user.has_role("admin", "editor") is True


async def test_has_all_roles(user, db):
    await user.assign_role("admin", "editor")
    assert await user.has_all_roles("admin", "editor") is True


async def test_has_all_roles_missing_one(user, db):
    await user.assign_role("admin")
    assert await user.has_all_roles("admin", "editor") is False


async def test_get_role_names(user, db):
    await user.assign_role("admin", "editor")
    names = await user.get_role_names()
    assert set(names) == {"admin", "editor"}


async def test_remove_role(user, db):
    await user.assign_role("admin", "editor")
    await user.remove_role("admin")
    assert await user.has_role("admin") is False
    assert await user.has_role("editor") is True



# ── Direct permissions ────────────────────────────────────────────────────────

async def test_give_and_can_permission(user, db):
    await user.give_permission("edit:posts")
    assert await user.can("edit:posts") is True


async def test_cannot(user, db):
    assert await user.cannot("edit:posts") is True


async def test_can_any_permission(user, db):
    await user.give_permission("read:posts")
    assert await user.can("edit:posts", "read:posts") is True


async def test_has_all_permissions(user, db):
    await user.give_permission("read:posts", "edit:posts")
    assert await user.has_all_permissions("read:posts", "edit:posts") is True


async def test_has_all_permissions_missing_one(user, db):
    await user.give_permission("read:posts")
    assert await user.has_all_permissions("read:posts", "edit:posts") is False


async def test_revoke_permission(user, db):
    await user.give_permission("edit:posts", "read:posts")
    await user.revoke_permission("edit:posts")
    assert await user.can("edit:posts") is False
    assert await user.can("read:posts") is True



async def test_get_all_permissions(user, db):
    await user.give_permission("read:posts", "edit:posts")
    perms = await user.get_all_permissions()
    assert set(perms) == {"read:posts", "edit:posts"}


# ── Permissions via role ──────────────────────────────────────────────────────

async def test_can_via_role(user, db):
    role = await Role.find_or_create("editor")
    await role.give_permission("edit:posts")
    await user.assign_role("editor")
    assert await user.can("edit:posts") is True


async def test_get_all_permissions_includes_role_perms(user, db):
    role = await Role.find_or_create("admin")
    await role.give_permission("manage:users")
    await user.assign_role("admin")
    await user.give_permission("read:posts")
    perms = await user.get_all_permissions()
    assert "manage:users" in perms
    assert "read:posts" in perms


# ── Role model ────────────────────────────────────────────────────────────────

async def test_role_give_and_has_permission(db):
    role = await Role.find_or_create("mod")
    await role.give_permission("edit:posts")
    assert await role.has_permission("edit:posts") is True


async def test_role_revoke_permission(db):
    role = await Role.find_or_create("mod2")
    await role.give_permission("edit:posts")
    await role.revoke_permission("edit:posts")
    assert await role.has_permission("edit:posts") is False



# ── with_role / without_role ──────────────────────────────────────────────────

async def test_with_role(user, other_user, db):
    await user.assign_role("admin")
    qs = await UserModel.with_role("admin")
    users = await qs
    ids = [u.id for u in users]
    assert user.id in ids
    assert other_user.id not in ids


async def test_without_role(user, other_user, db):
    await user.assign_role("admin")
    qs = await UserModel.without_role("admin")
    users = await qs
    ids = [u.id for u in users]
    assert user.id not in ids
    assert other_user.id in ids


async def test_with_role_empty_when_none_assigned(db):
    qs = await UserModel.with_role("admin")
    users = await qs
    assert users == []


async def test_without_role_returns_all_when_none_assigned(user, other_user, db):
    qs = await UserModel.without_role("admin")
    users = await qs
    assert len(users) == 2


async def test_with_role_multiple(user, other_user, db):
    await user.assign_role("admin")
    await other_user.assign_role("editor")
    qs = await UserModel.with_role("admin", "editor")
    users = await qs
    ids = {u.id for u in users}
    assert user.id in ids
    assert other_user.id in ids
