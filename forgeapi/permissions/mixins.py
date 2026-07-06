import logging

from tortoise.models import Model

from .models import Permission, Role, ModelHasRole, ModelHasPermission

logger = logging.getLogger("forgeapi.permissions")


class PermissionsMixin(Model):
    """Add to any Tortoise model to get Spatie-style roles and permissions.

    Uses two polymorphic pivot tables (``model_has_roles``,
    ``model_has_permissions``) so no per-model junction tables are created.
    ``model_type`` is the lowercase class name.

    Usage::

        from forgeapi.permissions import PermissionsMixin

        class User(PermissionsMixin):
            id    = fields.IntField(pk=True)
            email = fields.CharField(max_length=255, unique=True)

            class Meta:
                table = "users"

    Add ``"forgeapi.permissions.models"`` to your Tortoise ``apps`` config,
    then run migrations to create the permission tables.
    """

    class Meta:
        abstract = True

    @property
    def _model_type(self) -> str:
        return self.__class__.__name__.lower()

    # ── Permission checks ─────────────────────────────────────────────────────

    async def can(self, *permissions: str) -> bool:
        """``True`` if the model has **any** of the given permissions (direct or via role)."""
        names = list(permissions)

        if await ModelHasPermission.filter(
            model_type=self._model_type,
            model_id=self.pk,
            permission__name__in=names,
        ).exists():
            return True

        role_ids = await ModelHasRole.filter(
            model_type=self._model_type,
            model_id=self.pk,
        ).values_list("role_id", flat=True)

        if role_ids:
            return await Permission.filter(
                name__in=names,
                roles__id__in=list(role_ids),
            ).exists()

        return False

    async def cannot(self, *permissions: str) -> bool:
        return not await self.can(*permissions)

    async def has_all_permissions(self, *permissions: str) -> bool:
        """``True`` only if the model has **all** of the given permissions."""
        all_perms = set(await self.get_all_permissions())
        return set(permissions).issubset(all_perms)

    async def get_all_permissions(self) -> list[str]:
        """All permission names — direct + via roles, deduplicated."""
        direct = set(
            await ModelHasPermission.filter(
                model_type=self._model_type,
                model_id=self.pk,
            ).values_list("permission__name", flat=True)
        )

        role_ids = await ModelHasRole.filter(
            model_type=self._model_type,
            model_id=self.pk,
        ).values_list("role_id", flat=True)

        via_roles: set[str] = set()
        if role_ids:
            via_roles = set(
                await Permission.filter(
                    roles__id__in=list(role_ids),
                ).values_list("name", flat=True)
            )

        return list(direct | via_roles)

    # ── Direct permissions ────────────────────────────────────────────────────

    async def give_permission(self, *permissions: str) -> None:
        names = list(permissions)
        existing = await Permission.filter(name__in=names).all()
        existing_names = {p.name for p in existing}
        missing = [n for n in names if n not in existing_names]
        if missing:
            await Permission.bulk_create(
                [Permission(name=n) for n in missing],
                ignore_conflicts=True,
            )
            existing = await Permission.filter(name__in=names).all()
        await ModelHasPermission.bulk_create(
            [
                ModelHasPermission(
                    model_type=self._model_type,
                    model_id=self.pk,
                    permission_id=p.pk,
                )
                for p in existing
            ],
            ignore_conflicts=True,
        )

    async def revoke_permission(self, *permissions: str) -> None:
        perm_ids = await Permission.filter(name__in=list(permissions)).values_list("id", flat=True)
        if perm_ids:
            await ModelHasPermission.filter(
                model_type=self._model_type,
                model_id=self.pk,
                permission_id__in=list(perm_ids),
            ).delete()

    async def sync_permissions(self, permissions: list[str]) -> None:
        await ModelHasPermission.filter(
            model_type=self._model_type,
            model_id=self.pk,
        ).delete()
        await self.give_permission(*permissions)

    # ── Roles ─────────────────────────────────────────────────────────────────

    async def has_role(self, *roles: str) -> bool:
        """``True`` if the model has **any** of the given roles."""
        role_ids = await Role.filter(name__in=list(roles)).values_list("id", flat=True)
        if not role_ids:
            return False
        return await ModelHasRole.filter(
            model_type=self._model_type,
            model_id=self.pk,
            role_id__in=list(role_ids),
        ).exists()

    async def has_all_roles(self, *roles: str) -> bool:
        """``True`` only if the model has **all** of the given roles."""
        requested_ids = set(
            await Role.filter(name__in=list(roles)).values_list("id", flat=True)
        )
        if len(requested_ids) != len(roles):
            return False
        held_ids = set(
            await ModelHasRole.filter(
                model_type=self._model_type,
                model_id=self.pk,
                role_id__in=list(requested_ids),
            ).values_list("role_id", flat=True)
        )
        return held_ids == requested_ids

    async def get_role_names(self) -> list[str]:
        return list(
            await ModelHasRole.filter(
                model_type=self._model_type,
                model_id=self.pk,
            ).values_list("role__name", flat=True)
        )

    async def assign_role(self, *roles: str) -> None:
        names = list(roles)
        existing = await Role.filter(name__in=names).all()
        existing_names = {r.name for r in existing}
        missing = [n for n in names if n not in existing_names]
        if missing:
            await Role.bulk_create(
                [Role(name=n) for n in missing],
                ignore_conflicts=True,
            )
            existing = await Role.filter(name__in=names).all()
        await ModelHasRole.bulk_create(
            [
                ModelHasRole(
                    model_type=self._model_type,
                    model_id=self.pk,
                    role_id=r.pk,
                )
                for r in existing
            ],
            ignore_conflicts=True,
        )

    async def remove_role(self, *roles: str) -> None:
        role_ids = await Role.filter(name__in=list(roles)).values_list("id", flat=True)
        if role_ids:
            await ModelHasRole.filter(
                model_type=self._model_type,
                model_id=self.pk,
                role_id__in=list(role_ids),
            ).delete()

    async def sync_roles(self, roles: list[str]) -> None:
        await ModelHasRole.filter(
            model_type=self._model_type,
            model_id=self.pk,
        ).delete()
        await self.assign_role(*roles)

    # ── Class-level role filters ──────────────────────────────────────────────

    @classmethod
    async def with_role(cls, *roles: str):
        """Return a QuerySet of instances that have any of the given roles."""
        ids = await ModelHasRole.filter(
            model_type=cls.__name__.lower(),
            role__name__in=list(roles),
        ).values_list("model_id", flat=True)
        return cls.filter(id__in=ids)

    @classmethod
    async def without_role(cls, *roles: str):
        """Return a QuerySet of instances that have none of the given roles."""
        ids = await ModelHasRole.filter(
            model_type=cls.__name__.lower(),
            role__name__in=list(roles),
        ).values_list("model_id", flat=True)
        return cls.exclude(id__in=ids)
