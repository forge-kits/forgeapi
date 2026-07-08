from __future__ import annotations

import asyncio
import logging

from tortoise.models import Model
from tortoise.queryset import QuerySet

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
        """Lowercase class name used as the ``model_type`` discriminator in pivot tables.

        Example::

            class User(PermissionsMixin): ...
            user = User()
            assert user._model_type == "user"
        """
        return self.__class__.__name__.lower()

    def _clear_permission_cache(self) -> None:
        """Invalidate all in-memory permission caches on this instance.

        :meth:`get_all_permissions` stores fetched results under
        ``_perm_cache_<guard>`` keys.  Call this method after any mutation
        (grant / revoke / assign-role / remove-role) so that the next
        :meth:`can` / :meth:`get_all_permissions` call re-queries the DB.

        Example::

            await user.give_permission("edit:posts")
            user._clear_permission_cache()  # cache invalidated automatically by give_permission
        """
        for key in list(self.__dict__):
            if key.startswith("_perm_cache_"):
                del self.__dict__[key]

    # ── Permission checks ─────────────────────────────────────────────────────

    async def can(self, *permissions: str, guard: str = "api") -> bool:
        """Return ``True`` if the model has **any** of the given permissions (direct or via role).

        Checks both direct permissions (``model_has_permissions``) and
        permissions inherited through assigned roles in a single round-trip
        using ``asyncio.gather``.

        Args:
            *permissions: One or more permission names to test.
            guard:        Auth guard namespace (default ``"api"``).

        Returns:
            ``True`` when at least one permission is held, ``False`` otherwise.

        Example::

            if await user.can("edit:posts"):
                ...

            # Any of the listed permissions is enough:
            if await user.can("edit:posts", "admin"):
                ...

            # Custom guard:
            if await user.can("manage:settings", guard="web"):
                ...
        """
        names = list(permissions)

        direct_exists, role_ids = await asyncio.gather(
            ModelHasPermission.filter(
                model_type=self._model_type,
                model_id=self.pk,
                permission__name__in=names,
                permission__guard=guard,
            ).exists(),
            ModelHasRole.filter(
                model_type=self._model_type,
                model_id=self.pk,
                role__guard=guard,
            ).values_list("role_id", flat=True),
        )

        if direct_exists:
            return True

        if role_ids:
            return await Permission.filter(
                name__in=names,
                guard=guard,
                roles__id__in=list(role_ids),
            ).exists()

        return False

    async def cannot(self, *permissions: str, guard: str = "api") -> bool:
        """Return ``True`` if the model lacks **all** of the given permissions.

        Convenience inverse of :meth:`can`.

        Args:
            *permissions: One or more permission names to test.
            guard:        Auth guard namespace (default ``"api"``).

        Returns:
            ``True`` when none of the permissions are held.

        Example::

            if await user.cannot("delete:posts"):
                raise HTTPException(403, "Forbidden")
        """
        return not await self.can(*permissions, guard=guard)

    async def has_all_permissions(self, *permissions: str, guard: str = "api") -> bool:
        """Return ``True`` only if the model has **every** permission listed.

        Uses :meth:`get_all_permissions` (cached) and then checks set
        containment — no extra DB query on repeated calls within the same
        request lifecycle.

        Args:
            *permissions: Every permission name that must be held.
            guard:        Auth guard namespace (default ``"api"``).

        Returns:
            ``True`` only when all permissions are held simultaneously.

        Example::

            # True only if the user holds both:
            if await user.has_all_permissions("edit:posts", "publish:posts"):
                ...
        """
        all_perms = set(await self.get_all_permissions(guard=guard))
        return set(permissions).issubset(all_perms)

    async def get_all_permissions(self, guard: str = "api") -> list[str]:
        """Return all permission names held by this model — direct and via roles, deduplicated.

        Results are cached on the instance under ``_perm_cache_<guard>`` after
        the first call.  The cache is cleared automatically by any mutating
        method (:meth:`give_permission`, :meth:`revoke_permission`,
        :meth:`assign_role`, :meth:`remove_role`).

        Args:
            guard: Auth guard namespace (default ``"api"``).

        Returns:
            Deduplicated list of permission name strings.

        Example::

            perms = await user.get_all_permissions()
            # ["edit:posts", "view:dashboard", "delete:comments"]

            # Subsequent calls within the same request hit the cache:
            perms_again = await user.get_all_permissions()
        """
        cache_key = f"_perm_cache_{guard}"
        cached = self.__dict__.get(cache_key)
        if cached is not None:
            return cached

        direct_names, role_ids = await asyncio.gather(
            ModelHasPermission.filter(
                model_type=self._model_type,
                model_id=self.pk,
                permission__guard=guard,
            ).values_list("permission__name", flat=True),
            ModelHasRole.filter(
                model_type=self._model_type,
                model_id=self.pk,
                role__guard=guard,
            ).values_list("role_id", flat=True),
        )

        direct = set(direct_names)
        via_roles: set[str] = set()
        if role_ids:
            via_roles = set(
                await Permission.filter(
                    guard=guard,
                    roles__id__in=list(role_ids),
                ).values_list("name", flat=True)
            )

        result = list(direct | via_roles)
        self.__dict__[cache_key] = result
        return result

    # ── Direct permissions ────────────────────────────────────────────────────

    async def give_permission(self, *permissions: str) -> None:
        """Attach permissions directly to this model instance.

        Permissions that do not yet exist in the ``permissions`` table are
        created automatically via ``bulk_create(ignore_conflicts=True)``.
        Already-held permissions are silently skipped.
        Clears the in-memory permission cache afterwards.

        Args:
            *permissions: One or more permission name strings.

        Example::

            await user.give_permission("edit:posts")
            await user.give_permission("create:posts", "delete:posts")

            # New permission names are auto-created:
            await user.give_permission("brand_new:action")
        """
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
        self._clear_permission_cache()

    async def revoke_permission(self, *permissions: str) -> None:
        """Remove direct permissions from this model instance.

        Permissions that the model does not hold are silently ignored.
        Clears the in-memory permission cache afterwards.

        Args:
            *permissions: One or more permission name strings to revoke.

        Example::

            await user.revoke_permission("delete:posts")

            # Revoking a permission the user never had is a no-op:
            await user.revoke_permission("nonexistent:action")

            # Revoke multiple at once:
            await user.revoke_permission("edit:posts", "create:posts")
        """
        perm_ids = await Permission.filter(name__in=list(permissions)).values_list("id", flat=True)
        if perm_ids:
            await ModelHasPermission.filter(
                model_type=self._model_type,
                model_id=self.pk,
                permission_id__in=list(perm_ids),
            ).delete()
        self._clear_permission_cache()

    # ── Roles ─────────────────────────────────────────────────────────────────

    async def has_role(self, *roles: str, guard: str = "api") -> bool:
        """Return ``True`` if the model has **any** of the given roles.

        Args:
            *roles: One or more role names to test.
            guard:  Auth guard namespace (default ``"api"``).

        Returns:
            ``True`` when at least one role is held, ``False`` otherwise.

        Example::

            if await user.has_role("admin"):
                ...

            # Any of the listed roles is sufficient:
            if await user.has_role("admin", "moderator"):
                ...
        """
        role_ids = await Role.filter(name__in=list(roles), guard=guard).values_list("id", flat=True)
        if not role_ids:
            return False
        return await ModelHasRole.filter(
            model_type=self._model_type,
            model_id=self.pk,
            role_id__in=list(role_ids),
        ).exists()

    async def has_all_roles(self, *roles: str, guard: str = "api") -> bool:
        """Return ``True`` only if the model holds **every** role listed.

        Returns ``False`` early if any of the requested role names do not
        even exist in the ``roles`` table (they cannot be held).

        Args:
            *roles: Every role name that must be held.
            guard:  Auth guard namespace (default ``"api"``).

        Returns:
            ``True`` only when all roles are held simultaneously.

        Example::

            # True only if the user is both admin AND moderator:
            if await user.has_all_roles("admin", "moderator"):
                ...
        """
        roles_dedup = list(dict.fromkeys(roles))
        requested_ids = set(
            await Role.filter(name__in=roles_dedup, guard=guard).values_list("id", flat=True)
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
        """Return the names of all roles currently assigned to this model instance.

        Returns:
            List of role name strings (unordered).

        Example::

            await user.assign_role("admin", "editor")
            names = await user.get_role_names()
            # ["admin", "editor"]  (order may vary)
        """
        return list(
            await ModelHasRole.filter(
                model_type=self._model_type,
                model_id=self.pk,
            ).values_list("role__name", flat=True)
        )

    async def assign_role(self, *roles: str) -> None:
        """Assign one or more roles to this model instance.

        Roles that do not yet exist in the ``roles`` table are created
        automatically via ``bulk_create(ignore_conflicts=True)``.
        Already-assigned roles are silently skipped.
        Clears the in-memory permission cache afterwards.

        Args:
            *roles: One or more role name strings to assign.

        Example::

            await user.assign_role("editor")
            await user.assign_role("admin", "moderator")

            # New role names are auto-created:
            await user.assign_role("brand_new_role")
        """
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
        self._clear_permission_cache()

    async def remove_role(self, *roles: str) -> None:
        """Remove one or more roles from this model instance.

        Roles that are not currently assigned are silently ignored.
        Clears the in-memory permission cache afterwards.

        Args:
            *roles: One or more role name strings to remove.

        Example::

            await user.remove_role("editor")

            # No-op when the user doesn't have the role:
            await user.remove_role("nonexistent_role")

            # Remove multiple at once:
            await user.remove_role("admin", "moderator")
        """
        role_ids = await Role.filter(name__in=list(roles)).values_list("id", flat=True)
        if role_ids:
            await ModelHasRole.filter(
                model_type=self._model_type,
                model_id=self.pk,
                role_id__in=list(role_ids),
            ).delete()
        self._clear_permission_cache()

    # ── Class-level role filters ──────────────────────────────────────────────

    @classmethod
    async def with_role(cls, *roles: str, guard: str = "api") -> QuerySet:
        """Return a QuerySet of instances that have any of the given roles.

      Args:
          *roles: Role names to filter by.
          guard: Auth guard name.

      Returns:
          QuerySet — chain additional filters or await directly.

      Example:
          admins = await (await User.with_role("admin", "editor"))
          count  = await (await User.with_role("admin")).count()
      """
        ids = await ModelHasRole.filter(
            model_type=cls.__name__.lower(),
            role__name__in=list(roles),
            role__guard=guard,
        ).values_list("model_id", flat=True)
        return cls.filter(id__in=ids)

    @classmethod
    async def without_role(cls, *roles: str, guard: str = "api") -> QuerySet:
        """Return a QuerySet of instances that have **none** of the given roles.

        Args:
            *roles: Role names to exclude by.
            guard:  Auth guard name (default ``"api"``).

        Returns:
            QuerySet — chain additional filters or await directly.

        Example::

            # All users that are NOT admins:
            regular_users = await (await User.without_role("admin"))

            # Users that are neither admin nor moderator:
            plain = await (await User.without_role("admin", "moderator"))
            count = await (await User.without_role("admin")).count()
        """
        ids = await ModelHasRole.filter(
            model_type=cls.__name__.lower(),
            role__name__in=list(roles),
            role__guard=guard,
        ).values_list("model_id", flat=True)
        return cls.exclude(id__in=ids)
