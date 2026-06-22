from tortoise import fields
from tortoise.models import Model


class Permission(Model):
    id    = fields.IntField(pk=True)
    name  = fields.CharField(max_length=255, unique=True)
    guard = fields.CharField(max_length=100, default="api")

    class Meta:
        table = "permissions"
        app   = "permissions"

    def __str__(self) -> str:
        return self.name

    @classmethod
    async def find_or_create(cls, name: str, guard: str = "api") -> "Permission":
        perm, _ = await cls.get_or_create(name=name, defaults={"guard": guard})
        return perm


class Role(Model):
    id    = fields.IntField(pk=True)
    name  = fields.CharField(max_length=255, unique=True)
    guard = fields.CharField(max_length=100, default="api")

    permissions: fields.ManyToManyRelation[Permission] = fields.ManyToManyField(
        "permissions.Permission",
        related_name="roles",
        through="role_permissions",
    )

    class Meta:
        table = "roles"
        app   = "permissions"

    def __str__(self) -> str:
        return self.name

    @classmethod
    async def find_or_create(cls, name: str, guard: str = "api") -> "Role":
        role, _ = await cls.get_or_create(name=name, defaults={"guard": guard})
        return role

    async def give_permission(self, *names: str) -> None:
        for name in names:
            perm = await Permission.find_or_create(name)
            await self.permissions.add(perm)

    async def revoke_permission(self, *names: str) -> None:
        for name in names:
            perm = await Permission.get_or_none(name=name)
            if perm:
                await self.permissions.remove(perm)

    async def sync_permissions(self, names: list[str]) -> None:
        await self.permissions.clear()
        await self.give_permission(*names)

    async def has_permission(self, name: str) -> bool:
        return await self.permissions.filter(name=name).exists()
