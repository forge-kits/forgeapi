from tortoise import fields
from tortoise.models import Model


def _default_guard() -> str:
    from forgeapi.auth.facade import auth
    guard = auth._default
    if not guard:
        raise ValueError(
            "guard must be a non-empty string. "
            "Configure auth guards or pass guard= explicitly."
        )
    return guard


class Permission(Model):
    """A named permission that can be attached directly to a model or to a Role.

    Attributes:
        id:    Auto-increment primary key.
        name:  Permission identifier, e.g. ``"edit:posts"``.
        guard: Auth guard namespace. Always set — never NULL in practice.

    Example::

        perm = await Permission.find_or_create("edit:posts")
        print(perm)  # "edit:posts"
    """

    id    = fields.IntField(primary_key=True)
    name  = fields.CharField(max_length=255)
    guard = fields.CharField(max_length=100, null=True)

    class Meta:
        table           = "permissions"
        unique_together = [("name", "guard")]

    def __str__(self) -> str:
        return self.name

    @classmethod
    async def find_or_create(cls, name: str, guard: str | None = None) -> "Permission":
        """Fetch an existing permission or create it if it does not exist.

        Args:
            name:  Permission identifier, e.g. ``"delete:comments"``.
            guard: Auth guard namespace. Omit to use ``auth._default``.

        Raises:
            ValueError: if *guard* resolves to an empty string.

        Example::

            perm = await Permission.find_or_create("publish:articles")
            perm = await Permission.find_or_create("admin:panel", guard="web")
        """
        _guard = guard or _default_guard()
        obj, _ = await cls.get_or_create(name=name, guard=_guard)
        return obj


class Role(Model):
    """A named role that bundles multiple permissions together.

    Roles are assigned to model instances (e.g. ``User``) via the
    :class:`ModelHasRole` pivot.  Permissions are attached to roles via
    the ``role_permissions`` many-to-many through table.

    Attributes:
        id:          Auto-increment primary key.
        name:        Role identifier, e.g. ``"admin"``.
        guard:       Auth guard namespace. Always set — never NULL in practice.
        permissions: M2M relation to :class:`Permission`.

    Example::

        role = await Role.find_or_create("editor")
        await role.give_permission("create:posts", "edit:posts")
        print(role)  # "editor"
    """

    id    = fields.IntField(primary_key=True)
    name  = fields.CharField(max_length=255)
    guard = fields.CharField(max_length=100, null=True)

    permissions: fields.ManyToManyRelation["Permission"] = fields.ManyToManyField(
        "models.Permission",
        related_name="roles",
        through="role_permissions",
    )

    class Meta:
        table           = "roles"
        unique_together = [("name", "guard")]

    def __str__(self) -> str:
        return self.name

    @classmethod
    async def find_or_create(cls, name: str, guard: str | None = None) -> "Role":
        """Fetch an existing role or create it if it does not exist.

        Args:
            name:  Role identifier, e.g. ``"moderator"``.
            guard: Auth guard namespace. Omit to use ``auth._default``.

        Raises:
            ValueError: if *guard* resolves to an empty string.

        Example::

            admin      = await Role.find_or_create("admin")
            web_admin  = await Role.find_or_create("admin", guard="web")
        """
        _guard = guard or _default_guard()
        obj, _ = await cls.get_or_create(name=name, guard=_guard)
        return obj

    async def give_permission(self, *names: str) -> None:
        """Attach permissions to this role, creating them if they do not exist.

        Permissions are created in the same guard namespace as this role (``self.guard``).

        Args:
            *names: One or more permission names to attach.

        Example::

            role = await Role.find_or_create("editor")
            await role.give_permission("create:posts", "edit:posts")
        """
        name_list = list(names)
        existing = await Permission.filter(name__in=name_list, guard=self.guard).all()
        existing_names = {p.name for p in existing}
        missing = [n for n in name_list if n not in existing_names]
        if missing:
            await Permission.bulk_create(
                [Permission(name=n, guard=self.guard) for n in missing],
                ignore_conflicts=True,
            )
            existing = await Permission.filter(name__in=name_list, guard=self.guard).all()
        if existing:
            await self.permissions.add(*existing)

    async def revoke_permission(self, *names: str) -> None:
        """Detach permissions from this role.

        Looks up permissions in the same guard namespace as this role (``self.guard``).
        Non-linked permissions are silently ignored.

        Args:
            *names: One or more permission names to detach.

        Example::

            await role.revoke_permission("delete:posts")
        """
        perms = await Permission.filter(name__in=list(names), guard=self.guard).all()
        if perms:
            await self.permissions.remove(*perms)

    async def has_permission(self, name: str) -> bool:
        """Return ``True`` if this role has the given permission.

        Looks up within the role's own guard namespace (``self.guard``).

        Args:
            name: Permission name to check, e.g. ``"edit:posts"``.

        Example::

            assert await role.has_permission("edit:posts") is True
        """
        return await self.permissions.filter(name=name, guard=self.guard).exists()


class ModelHasRole(Model):
    """Polymorphic model → role pivot."""

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
