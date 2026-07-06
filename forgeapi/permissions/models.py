from tortoise import fields
from tortoise.models import Model


class Permission(Model):
    id    = fields.IntField(pk=True)
    name  = fields.CharField(max_length=255, unique=True)
    guard = fields.CharField(max_length=100, default="api")

    class Meta:
        table = "permissions"

    def __str__(self) -> str:
        return self.name

    @classmethod
    async def find_or_create(cls, name: str, guard: str = "api") -> "Permission":
        obj, _ = await cls.get_or_create(name=name, defaults={"guard": guard})
        return obj


class Role(Model):
    id    = fields.IntField(pk=True)
    name  = fields.CharField(max_length=255, unique=True)
    guard = fields.CharField(max_length=100, default="api")

    permissions: fields.ManyToManyRelation["Permission"] = fields.ManyToManyField(
        "models.Permission",
        related_name="roles",
        through="role_permissions",
    )

    class Meta:
        table = "roles"

    def __str__(self) -> str:
        return self.name

    @classmethod
    async def find_or_create(cls, name: str, guard: str = "api") -> "Role":
        obj, _ = await cls.get_or_create(name=name, defaults={"guard": guard})
        return obj

    async def give_permission(self, *names: str) -> None:
        name_list = list(names)
        existing = await Permission.filter(name__in=name_list).all()
        existing_names = {p.name for p in existing}
        missing = [n for n in name_list if n not in existing_names]
        if missing:
            await Permission.bulk_create(
                [Permission(name=n) for n in missing],
                ignore_conflicts=True,
            )
            existing = await Permission.filter(name__in=name_list).all()
        if existing:
            await self.permissions.add(*existing)

    async def revoke_permission(self, *names: str) -> None:
        perms = await Permission.filter(name__in=list(names)).all()
        if perms:
            await self.permissions.remove(*perms)

    async def sync_permissions(self, names: list[str]) -> None:
        await self.permissions.clear()
        await self.give_permission(*names)

    async def has_permission(self, name: str) -> bool:
        return await self.permissions.filter(name=name).exists()


class ModelHasRole(Model):
    """Polymorphic model → role pivot.

    ``model_type`` is the lowercase class name (e.g. ``"user"``).
    ``model_id``   is the PK of that model instance.
    """

    model_type = fields.CharField(max_length=100)
    model_id   = fields.BigIntField()
    role: fields.ForeignKeyRelation[Role] = fields.ForeignKeyField(
        "models.Role",
        related_name="model_has_roles",
        on_delete=fields.CASCADE,
    )

    class Meta:
        table           = "model_has_roles"
        unique_together = [("model_type", "model_id", "role_id")]


class ModelHasPermission(Model):
    """Polymorphic model → direct permission pivot."""

    model_type = fields.CharField(max_length=100)
    model_id   = fields.BigIntField()
    permission: fields.ForeignKeyRelation[Permission] = fields.ForeignKeyField(
        "models.Permission",
        related_name="model_has_permissions",
        on_delete=fields.CASCADE,
    )

    class Meta:
        table           = "model_has_permissions"
        unique_together = [("model_type", "model_id", "permission_id")]
