from __future__ import annotations

from typing import Any, Iterable


class ModelObserver:
    """Base class for model observers — override only the hooks you need.

    Register on a model with :meth:`~forgeapi.database.ModelMixin.observe`::

        class PostObserver(ModelObserver):
            async def created(self, instance) -> None:
                await Cache.forget("posts:list")

            async def updated(self, instance) -> None:
                await Cache.forget(f"posts:{instance.id}")

            async def deleted(self, instance) -> None:
                await Cache.forget("posts:list")
                await Cache.forget(f"posts:{instance.id}")

        # In app lifespan or startup:
        Post.observe(PostObserver)   # class — auto-instantiated
        Post.observe(PostObserver()) # or instance
    """


_HOOK_PRE_SAVE = ("saving", "creating", "updating")
_HOOK_POST_SAVE = ("saved", "created", "updated")


def _register_observer(model_class: type, observer: ModelObserver) -> None:
    """Wire all defined observer hooks to Tortoise signals."""
    from tortoise.signals import Signals

    has_pre = any(hasattr(observer, h) for h in _HOOK_PRE_SAVE)
    has_post = any(hasattr(observer, h) for h in _HOOK_POST_SAVE)
    has_pre_del = hasattr(observer, "deleting")
    has_post_del = hasattr(observer, "deleted")

    if has_pre:
        async def _on_pre_save(
            sender: type,
            instance: Any,
            using_db: Any,
            update_fields: Iterable[str] | None,
        ) -> None:
            # _saved_in_db is False when the record doesn't exist in DB yet.
            is_new = not getattr(instance, "_saved_in_db", False)
            if hasattr(observer, "saving"):
                await observer.saving(instance)
            if is_new and hasattr(observer, "creating"):
                await observer.creating(instance)
            elif not is_new and hasattr(observer, "updating"):
                await observer.updating(instance)

        model_class.register_listener(Signals.pre_save, _on_pre_save)

    if has_post:
        async def _on_post_save(
            sender: type,
            instance: Any,
            created: bool,
            using_db: Any,
            update_fields: Iterable[str] | None,
        ) -> None:
            if hasattr(observer, "saved"):
                await observer.saved(instance)
            if created and hasattr(observer, "created"):
                await observer.created(instance)
            elif not created and hasattr(observer, "updated"):
                await observer.updated(instance)

        model_class.register_listener(Signals.post_save, _on_post_save)

    if has_pre_del:
        async def _on_pre_delete(sender: type, instance: Any, using_db: Any) -> None:
            await observer.deleting(instance)

        model_class.register_listener(Signals.pre_delete, _on_pre_delete)

    if has_post_del:
        async def _on_post_delete(sender: type, instance: Any, using_db: Any) -> None:
            await observer.deleted(instance)

        model_class.register_listener(Signals.post_delete, _on_post_delete)
