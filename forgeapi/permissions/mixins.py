from tortoise import fields
from tortoise.models import Model

from .models import Permission, Role


class PermissionsMixin(Model):
    """Add to your User model to get Spatie-like roles and permissions.

    Usage::

        from forgeapi.permissions import PermissionsMixin

        class User(PermissionsMixin):
            id    = fields.IntField(pk=True)
            name  = fields.CharField(max_length=255)
            email = fields.CharField(max_length=255, unique=True)

            class Meta:
                table = "users"

    Then add "forgeapi.permissions.models" to your TORTOISE_ORM apps config.
    """

    roles: fields.ManyToManyRelation[Role] = fields.ManyToManyField(
        "permissions.Role",
        related_name="users",
        through="user_roles",
    )
    direct_permissions: fields.ManyToManyRelation[Permission] = fields.ManyToManyField(
        "permissions.Permission",
        related_name="direct_users",
        through="user_permissions",
    )

    class Meta:
        abstract = True

    # ── Permission checks ─────────────────────────────────────────────────────

    async def can(self, *permissions: str) -> bool:
        """Return True if the user has ANY of the given permissions (direct or via role)."""
        names = list(permissions)
        if await self.direct_permissions.filter(name__in=names).exists():
            return True
        role_ids = list(await self.roles.all().values_list("id", flat=True))
        if role_ids:
            return await Permission.filter(name__in=names, roles__id__in=role_ids).exists()
        return False

    async def cannot(self, *permissions: str) -> bool:
        return not await self.can(*permissions)

    async def has_all_permissions(self, *permissions: str) -> bool:
        """Return True only if the user has ALL of the given permissions."""
        for perm in permissions:
            if not await self.can(perm):
                return False
        return True

    async def get_all_permissions(self) -> list[str]:
        """Return all permission names — direct + via roles, deduplicated."""
        direct = set(await self.direct_permissions.all().values_list("name", flat=True))
        role_ids = list(await self.roles.all().values_list("id", flat=True))
        via_roles: set[str] = set()
        if role_ids:
            via_roles = set(
                await Permission.filter(roles__id__in=role_ids).values_list("name", flat=True)
            )
        return list(direct | via_roles)

    # ── Direct permissions ────────────────────────────────────────────────────

    async def give_permission(self, *permissions: str) -> None:
        for name in permissions:
            perm = await Permission.find_or_create(name)
            await self.direct_permissions.add(perm)

    async def revoke_permission(self, *permissions: str) -> None:
        for name in permissions:
            perm = await Permission.get_or_none(name=name)
            if perm:
                await self.direct_permissions.remove(perm)

    async def sync_permissions(self, permissions: list[str]) -> None:
        await self.direct_permissions.clear()
        await self.give_permission(*permissions)

    # ── Roles ─────────────────────────────────────────────────────────────────

    async def has_role(self, *roles: str) -> bool:
        """Return True if the user has ANY of the given roles."""
        return await self.roles.filter(name__in=list(roles)).exists()

    async def has_all_roles(self, *roles: str) -> bool:
        """Return True only if the user has ALL of the given roles."""
        count = await self.roles.filter(name__in=list(roles)).count()
        return count == len(roles)

    async def get_role_names(self) -> list[str]:
        return list(await self.roles.all().values_list("name", flat=True))

    async def assign_role(self, *roles: str) -> None:
        for name in roles:
            role = await Role.find_or_create(name)
            await self.roles.add(role)

    async def remove_role(self, *roles: str) -> None:
        for name in roles:
            role = await Role.get_or_none(name=name)
            if role:
                await self.roles.remove(role)

    async def sync_roles(self, roles: list[str]) -> None:
        await self.roles.clear()
        await self.assign_role(*roles)
