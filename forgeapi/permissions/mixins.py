from __future__ import annotations

import asyncio
from typing import Union

from tortoise.models import Model
from tortoise.queryset import QuerySet

from forgeapi.logging import log
from .models import Permission, Role, ModelHasRole, ModelHasPermission

_log = log.channel("permissions")


def _resolve_guard(target: Union[type, object], guard: str | None) -> str:
    """Resolve the guard namespace for a model instance or class.

    Resolution order:
    1. Explicit *guard* kwarg.
    2. Reverse lookup in ``auth._guards``: find the guard whose ``user_model``
       matches this model class.
    3. ``auth._default``.

    Raises:
        ValueError: if the resolved guard is empty (auth not configured).
    """
    if guard is not None:
        if not guard:
            raise ValueError("guard must be a non-empty string.")
        return guard
    from forgeapi.auth.facade import auth
    cls = target if isinstance(target, type) else type(target)
    for name, g in auth._guards.items():
        if g.user_model is cls:
            return name
    default = auth._default
    if not default:
        raise ValueError(
            f"Cannot resolve guard for '{cls.__name__}': not registered in any "
            "auth guard and auth has no default configured."
        )
    return default


class PermissionsMixin(Model):
    """Add to any Tortoise model to get Spatie-style roles and permissions.

    Uses two polymorphic pivot tables (``model_has_roles``,
    ``model_has_permissions``) so no per-model junction tables are created.
    ``model_type`` is the lowercase class name.

    Guard resolution — all methods accept an optional ``guard`` kwarg:

    1. Explicit ``guard="worker"`` — use as-is.
    2. Omitted — reverse-lookup which guard has ``user_model == type(self)``
       (reads from the auth config, no extra code needed on the model).
    3. Not found — fall back to ``auth._default``.

    Usage::

        from forgeapi.permissions import PermissionsMixin

        class User(PermissionsMixin):
            id    = fields.IntField(primary_key=True)
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

    def _clear_permission_cache(self) -> None:
        """Invalidate all in-memory permission caches on this instance."""
        for key in list(self.__dict__):
            if key.startswith("_perm_cache_"):
                del self.__dict__[key]

    # ── Permission checks ─────────────────────────────────────────────────────

    async def can(self, *permissions: str, guard: str | None = None) -> bool:
        """Return ``True`` if the model has **any** of the given permissions (direct or via role).

        Checks both direct permissions (``model_has_permissions``) and
        permissions inherited through assigned roles in a single round-trip
        using ``asyncio.gather``.

        Args:
            *permissions: One or more permission names to test.
            guard:        Auth guard namespace. Omit to auto-resolve from auth config.

        Returns:
            ``True`` when at least one permission is held, ``False`` otherwise.

        Example::

            if await user.can("edit:posts"):
                ...

            if await worker.can("view:tasks"):   # guard resolved automatically
                ...
        """
        _guard = _resolve_guard(self, guard)
        names = list(permissions)

        direct_exists, role_ids = await asyncio.gather(
            ModelHasPermission.filter(
                model_type=self._model_type,
                model_id=self.pk,
                permission__name__in=names,
                permission__guard=_guard,
            ).exists(),
            ModelHasRole.filter(
                model_type=self._model_type,
                model_id=self.pk,
                role__guard=_guard,
            ).values_list("role_id", flat=True),
        )

        if direct_exists:
            return True

        if role_ids:
            return await Permission.filter(
                name__in=names,
                guard=_guard,
                roles__id__in=list(role_ids),
            ).exists()

        return False

    async def cannot(self, *permissions: str, guard: str | None = None) -> bool:
        """Return ``True`` if the model lacks **all** of the given permissions.

        Args:
            *permissions: One or more permission names to test.
            guard:        Auth guard namespace. Omit to auto-resolve from auth config.
        """
        return not await self.can(*permissions, guard=guard)

    async def has_all_permissions(self, *permissions: str, guard: str | None = None) -> bool:
        """Return ``True`` only if the model has **every** permission listed.

        Args:
            *permissions: Every permission name that must be held.
            guard:        Auth guard namespace. Omit to auto-resolve from auth config.

        Example::

            if await user.has_all_permissions("edit:posts", "publish:posts"):
                ...
        """
        all_perms = set(await self.get_all_permissions(guard=guard))
        return set(permissions).issubset(all_perms)

    async def get_all_permissions(self, guard: str | None = None) -> list[str]:
        """Return all permission names held by this model — direct and via roles, deduplicated.

        Results are cached on the instance under ``_perm_cache_<guard>`` after
        the first call. The cache is cleared automatically by any mutating method.

        Args:
            guard: Auth guard namespace. Omit to auto-resolve from auth config.

        Returns:
            Deduplicated list of permission name strings.
        """
        _guard = _resolve_guard(self, guard)
        cache_key = f"_perm_cache_{_guard}"
        cached = self.__dict__.get(cache_key)
        if cached is not None:
            return cached

        direct_names, role_ids = await asyncio.gather(
            ModelHasPermission.filter(
                model_type=self._model_type,
                model_id=self.pk,
                permission__guard=_guard,
            ).values_list("permission__name", flat=True),
            ModelHasRole.filter(
                model_type=self._model_type,
                model_id=self.pk,
                role__guard=_guard,
            ).values_list("role_id", flat=True),
        )

        direct = set(direct_names)
        via_roles: set[str] = set()
        if role_ids:
            via_roles = set(
                await Permission.filter(
                    guard=_guard,
                    roles__id__in=list(role_ids),
                ).values_list("name", flat=True)
            )

        result = list(direct | via_roles)
        self.__dict__[cache_key] = result
        return result

    # ── Direct permissions ────────────────────────────────────────────────────

    async def give_permission(self, *permissions: str, guard: str | None = None) -> None:
        """Attach permissions directly to this model instance.

        Permissions that do not yet exist are created automatically.
        Already-held permissions are silently skipped.
        Clears the in-memory permission cache afterwards.

        Args:
            *permissions: One or more permission name strings.
            guard:        Auth guard namespace. Omit to auto-resolve from auth config.

        Example::

            await user.give_permission("edit:posts")
            await worker.give_permission("view:tasks")   # guard resolved automatically
        """
        _guard = _resolve_guard(self, guard)
        names = list(permissions)
        existing = await Permission.filter(name__in=names, guard=_guard).all()
        existing_names = {p.name for p in existing}
        missing = [n for n in names if n not in existing_names]
        if missing:
            await Permission.bulk_create(
                [Permission(name=n, guard=_guard) for n in missing],
                ignore_conflicts=True,
            )
            existing = await Permission.filter(name__in=names, guard=_guard).all()
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
        self._clear_permission_cache()

    async def revoke_permission(self, *permissions: str, guard: str | None = None) -> None:
        """Remove direct permissions from this model instance.

        Permissions that the model does not hold are silently ignored.
        Clears the in-memory permission cache afterwards.

        Args:
            *permissions: One or more permission name strings to revoke.
            guard:        Auth guard namespace. Omit to auto-resolve from auth config.
        """
        _guard = _resolve_guard(self, guard)
        perm_ids = await Permission.filter(
            name__in=list(permissions), guard=_guard,
        ).values_list("id", flat=True)
        if perm_ids:
            await ModelHasPermission.filter(
                model_type=self._model_type,
                model_id=self.pk,
                permission_id__in=list(perm_ids),
            ).delete()
        self._clear_permission_cache()

    # ── Roles ─────────────────────────────────────────────────────────────────

    async def has_role(self, *roles: str, guard: str | None = None) -> bool:
        """Return ``True`` if the model has **any** of the given roles.

        Args:
            *roles: One or more role names to test.
            guard:  Auth guard namespace. Omit to auto-resolve from auth config.

        Example::

            if await user.has_role("admin"):
                ...

            if await worker.has_role("supervisor"):   # guard resolved automatically
                ...
        """
        _guard = _resolve_guard(self, guard)
        role_ids = await Role.filter(name__in=list(roles), guard=_guard).values_list("id", flat=True)
        if not role_ids:
            return False
        return await ModelHasRole.filter(
            model_type=self._model_type,
            model_id=self.pk,
            role_id__in=list(role_ids),
        ).exists()

    async def has_all_roles(self, *roles: str, guard: str | None = None) -> bool:
        """Return ``True`` only if the model holds **every** role listed.

        Args:
            *roles: Every role name that must be held.
            guard:  Auth guard namespace. Omit to auto-resolve from auth config.

        Example::

            if await user.has_all_roles("admin", "moderator"):
                ...
        """
        _guard = _resolve_guard(self, guard)
        roles_dedup = list(dict.fromkeys(roles))
        requested_ids = set(
            await Role.filter(name__in=roles_dedup, guard=_guard).values_list("id", flat=True)
        )
        if len(requested_ids) != len(roles_dedup):
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
        """Return the names of all roles currently assigned to this model instance."""
        return list(
            await ModelHasRole.filter(
                model_type=self._model_type,
                model_id=self.pk,
            ).values_list("role__name", flat=True)
        )

    async def assign_role(self, *roles: str, guard: str | None = None) -> None:
        """Assign one or more roles to this model instance.

        Roles that do not yet exist are created automatically.
        Already-assigned roles are silently skipped.
        Clears the in-memory permission cache afterwards.

        Args:
            *roles: One or more role name strings to assign.
            guard:  Auth guard namespace. Omit to auto-resolve from auth config.

        Example::

            await user.assign_role("editor")
            await worker.assign_role("supervisor")   # guard resolved automatically
        """
        _guard = _resolve_guard(self, guard)
        names = list(roles)
        existing = await Role.filter(name__in=names, guard=_guard).all()
        existing_names = {r.name for r in existing}
        missing = [n for n in names if n not in existing_names]
        if missing:
            await Role.bulk_create(
                [Role(name=n, guard=_guard) for n in missing],
                ignore_conflicts=True,
            )
            existing = await Role.filter(name__in=names, guard=_guard).all()
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
        self._clear_permission_cache()

    async def remove_role(self, *roles: str, guard: str | None = None) -> None:
        """Remove one or more roles from this model instance.

        Roles that are not currently assigned are silently ignored.
        Clears the in-memory permission cache afterwards.

        Args:
            *roles: One or more role name strings to remove.
            guard:  Auth guard namespace. Omit to auto-resolve from auth config.
        """
        _guard = _resolve_guard(self, guard)
        role_ids = await Role.filter(
            name__in=list(roles), guard=_guard,
        ).values_list("id", flat=True)
        if role_ids:
            await ModelHasRole.filter(
                model_type=self._model_type,
                model_id=self.pk,
                role_id__in=list(role_ids),
            ).delete()
        self._clear_permission_cache()

    # ── Class-level role filters ──────────────────────────────────────────────

    @classmethod
    async def with_role(cls, *roles: str, guard: str | None = None) -> QuerySet:
        """Return a QuerySet of instances that have any of the given roles.

        Args:
            *roles: Role names to filter by.
            guard:  Auth guard namespace. Omit to auto-resolve from auth config.

        Example::

            admins = await (await User.with_role("admin"))
        """
        _guard = _resolve_guard(cls, guard)
        ids = await ModelHasRole.filter(
            model_type=cls.__name__.lower(),
            role__name__in=list(roles),
            role__guard=_guard,
        ).values_list("model_id", flat=True)
        return cls.filter(id__in=ids)

    @classmethod
    async def without_role(cls, *roles: str, guard: str | None = None) -> QuerySet:
        """Return a QuerySet of instances that have **none** of the given roles.

        Args:
            *roles: Role names to exclude by.
            guard:  Auth guard namespace. Omit to auto-resolve from auth config.

        Example::

            regular_users = await (await User.without_role("admin"))
        """
        _guard = _resolve_guard(cls, guard)
        ids = await ModelHasRole.filter(
            model_type=cls.__name__.lower(),
            role__name__in=list(roles),
            role__guard=_guard,
        ).values_list("model_id", flat=True)
        return cls.exclude(id__in=ids)
