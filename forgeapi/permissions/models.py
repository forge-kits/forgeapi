from tortoise import fields
from tortoise.models import Model


class Permission(Model):
    """A named permission that can be attached directly to a model or to a Role.

    Attributes:
        id:    Auto-increment primary key.
        name:  Unique permission identifier, e.g. ``"edit:posts"``.
        guard: Auth guard namespace (default ``"api"``).

    Example::

        perm = await Permission.find_or_create("edit:posts")
        print(perm)  # "edit:posts"
    """

    id    = fields.IntField(pk=True)
    name  = fields.CharField(max_length=255, unique=True)
    guard = fields.CharField(max_length=100, default="api")

    class Meta:
        table = "permissions"

    def __str__(self) -> str:
        """Return the permission name, e.g. ``"edit:posts"``."""
        return self.name

    @classmethod
    async def find_or_create(cls, name: str, guard: str = "api") -> "Permission":
        """Fetch an existing permission or create it if it does not exist.

        Args:
            name:  Unique permission identifier, e.g. ``"delete:comments"``.
            guard: Auth guard namespace (default ``"api"``).

        Returns:
            The existing or newly created :class:`Permission` instance.

        Example::

            perm = await Permission.find_or_create("publish:articles")
            perm = await Permission.find_or_create("admin:panel", guard="web")
        """
        obj, _ = await cls.get_or_create(name=name, defaults={"guard": guard})
        return obj


class Role(Model):
    """A named role that bundles multiple permissions together.

    Roles are assigned to model instances (e.g. ``User``) via the
    :class:`ModelHasRole` pivot.  Permissions are attached to roles via
    the ``role_permissions`` many-to-many through table.

    Attributes:
        id:          Auto-increment primary key.
        name:        Unique role identifier, e.g. ``"admin"``.
        guard:       Auth guard namespace (default ``"api"``).
        permissions: M2M relation to :class:`Permission`.

    Example::

        role = await Role.find_or_create("editor")
        await role.give_permission("create:posts", "edit:posts")
        print(role)  # "editor"
    """

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
        """Return the role name, e.g. ``"admin"``."""
        return self.name

    @classmethod
    async def find_or_create(cls, name: str, guard: str = "api") -> "Role":
        """Fetch an existing role or create it if it does not exist.

        Args:
            name:  Unique role identifier, e.g. ``"moderator"``.
            guard: Auth guard namespace (default ``"api"``).

        Returns:
            The existing or newly created :class:`Role` instance.

        Example::

            admin = await Role.find_or_create("admin")
            web_admin = await Role.find_or_create("admin", guard="web")
        """
        obj, _ = await cls.get_or_create(name=name, defaults={"guard": guard})
        return obj

    async def give_permission(self, *names: str) -> None:
        """Attach permissions to this role, creating them if they do not exist.

        Missing permissions are bulk-created with ``ignore_conflicts=True``
        before being linked via the ``role_permissions`` M2M table.

        Args:
            *names: One or more permission names to attach.

        Example::

            role = await Role.find_or_create("editor")
            await role.give_permission("create:posts", "edit:posts", "delete:posts")

            # Works even if "publish:posts" doesn't exist yet — it will be created.
            await role.give_permission("publish:posts")
        """
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
        """Detach permissions from this role.

        Permissions that are not currently linked are silently ignored.

        Args:
            *names: One or more permission names to detach.

        Example::

            role = await Role.find_or_create("editor")
            await role.revoke_permission("delete:posts")

            # Revoking a non-existent link is a no-op:
            await role.revoke_permission("does_not_exist")
        """
        perms = await Permission.filter(name__in=list(names)).all()
        if perms:
            await self.permissions.remove(*perms)

    async def has_permission(self, name: str, guard: str = "api") -> bool:
        """Return ``True`` if this role has the given permission.

        Args:
            name:  Permission name to check, e.g. ``"edit:posts"``.
            guard: Auth guard namespace (default ``"api"``).

        Returns:
            ``True`` if the permission is linked to this role, ``False`` otherwise.

        Example::

            role = await Role.find_or_create("editor")
            await role.give_permission("edit:posts")

            assert await role.has_permission("edit:posts") is True
            assert await role.has_permission("delete:posts") is False
        """
        return await self.permissions.filter(name=name, guard=guard).exists()


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
