"""Tests for ModelObserver and ModelMixin.observe()."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from forgeapi.database.observer import ModelObserver, _register_observer
from forgeapi.database.model import ModelMixin


# ---------------------------------------------------------------------------
# Helpers — fake model & instance without Tortoise DB
# ---------------------------------------------------------------------------

def make_fake_model():
    """Return a model class with a mocked register_listener."""
    listeners: dict = {}

    class FakeModel(ModelMixin):
        _saved_in_db = False

        @classmethod
        def register_listener(cls, signal, handler):
            listeners.setdefault(signal, []).append(handler)

        @classmethod
        def get_listeners(cls):
            return listeners

    return FakeModel, listeners


def make_instance(saved_in_db: bool = False):
    inst = MagicMock()
    inst._saved_in_db = saved_in_db
    inst.pk = None if not saved_in_db else 1
    return inst


# ---------------------------------------------------------------------------
# Observer registration
# ---------------------------------------------------------------------------

class TestObserverRegistration:
    def test_class_is_auto_instantiated(self):
        FakeModel, listeners = make_fake_model()

        class Obs(ModelObserver):
            async def created(self, inst):
                pass

        FakeModel.observe(Obs)
        from tortoise.signals import Signals
        assert Signals.post_save in listeners

    def test_instance_accepted_directly(self):
        FakeModel, listeners = make_fake_model()

        class Obs(ModelObserver):
            async def created(self, inst):
                pass

        FakeModel.observe(Obs())
        from tortoise.signals import Signals
        assert Signals.post_save in listeners

    def test_no_pre_save_registered_when_no_pre_hooks(self):
        FakeModel, listeners = make_fake_model()

        class Obs(ModelObserver):
            async def created(self, inst):
                pass

        FakeModel.observe(Obs)
        from tortoise.signals import Signals
        assert Signals.pre_save not in listeners

    def test_no_delete_registered_when_no_delete_hooks(self):
        FakeModel, listeners = make_fake_model()

        class Obs(ModelObserver):
            async def created(self, inst):
                pass

        FakeModel.observe(Obs)
        from tortoise.signals import Signals
        assert Signals.pre_delete not in listeners
        assert Signals.post_delete not in listeners

    def test_all_signals_registered_when_all_hooks_defined(self):
        FakeModel, listeners = make_fake_model()

        class Obs(ModelObserver):
            async def creating(self, inst): pass
            async def created(self, inst): pass
            async def deleting(self, inst): pass
            async def deleted(self, inst): pass

        FakeModel.observe(Obs)
        from tortoise.signals import Signals
        assert Signals.pre_save in listeners
        assert Signals.post_save in listeners
        assert Signals.pre_delete in listeners
        assert Signals.post_delete in listeners


# ---------------------------------------------------------------------------
# post_save hooks — created / updated / saved
# ---------------------------------------------------------------------------

class TestPostSaveHooks:
    @pytest.mark.anyio
    async def test_created_called_on_insert(self):
        FakeModel, listeners = make_fake_model()
        obs = ModelObserver()
        obs.created = AsyncMock()
        _register_observer(FakeModel, obs)

        from tortoise.signals import Signals
        handler = listeners[Signals.post_save][0]
        inst = make_instance()
        await handler(FakeModel, inst, created=True, using_db=None, update_fields=None)

        obs.created.assert_awaited_once_with(inst)

    @pytest.mark.anyio
    async def test_updated_called_on_update(self):
        FakeModel, listeners = make_fake_model()
        obs = ModelObserver()
        obs.updated = AsyncMock()
        _register_observer(FakeModel, obs)

        from tortoise.signals import Signals
        handler = listeners[Signals.post_save][0]
        inst = make_instance(saved_in_db=True)
        await handler(FakeModel, inst, created=False, using_db=None, update_fields=None)

        obs.updated.assert_awaited_once_with(inst)

    @pytest.mark.anyio
    async def test_created_not_called_on_update(self):
        FakeModel, listeners = make_fake_model()
        obs = ModelObserver()
        obs.created = AsyncMock()
        obs.updated = AsyncMock()
        _register_observer(FakeModel, obs)

        from tortoise.signals import Signals
        handler = listeners[Signals.post_save][0]
        inst = make_instance(saved_in_db=True)
        await handler(FakeModel, inst, created=False, using_db=None, update_fields=None)

        obs.created.assert_not_awaited()
        obs.updated.assert_awaited_once()

    @pytest.mark.anyio
    async def test_saved_called_on_both_create_and_update(self):
        FakeModel, listeners = make_fake_model()
        obs = ModelObserver()
        obs.saved = AsyncMock()
        _register_observer(FakeModel, obs)

        from tortoise.signals import Signals
        handler = listeners[Signals.post_save][0]

        inst = make_instance()
        await handler(FakeModel, inst, created=True, using_db=None, update_fields=None)
        await handler(FakeModel, inst, created=False, using_db=None, update_fields=None)

        assert obs.saved.await_count == 2


# ---------------------------------------------------------------------------
# pre_save hooks — creating / updating / saving
# ---------------------------------------------------------------------------

class TestPreSaveHooks:
    @pytest.mark.anyio
    async def test_creating_called_for_new_record(self):
        FakeModel, listeners = make_fake_model()
        obs = ModelObserver()
        obs.creating = AsyncMock()
        _register_observer(FakeModel, obs)

        from tortoise.signals import Signals
        handler = listeners[Signals.pre_save][0]
        inst = make_instance(saved_in_db=False)
        await handler(FakeModel, inst, using_db=None, update_fields=None)

        obs.creating.assert_awaited_once_with(inst)

    @pytest.mark.anyio
    async def test_updating_called_for_existing_record(self):
        FakeModel, listeners = make_fake_model()
        obs = ModelObserver()
        obs.updating = AsyncMock()
        _register_observer(FakeModel, obs)

        from tortoise.signals import Signals
        handler = listeners[Signals.pre_save][0]
        inst = make_instance(saved_in_db=True)
        await handler(FakeModel, inst, using_db=None, update_fields=None)

        obs.updating.assert_awaited_once_with(inst)

    @pytest.mark.anyio
    async def test_saving_called_for_both(self):
        FakeModel, listeners = make_fake_model()
        obs = ModelObserver()
        obs.saving = AsyncMock()
        _register_observer(FakeModel, obs)

        from tortoise.signals import Signals
        handler = listeners[Signals.pre_save][0]

        inst_new = make_instance(saved_in_db=False)
        inst_existing = make_instance(saved_in_db=True)
        await handler(FakeModel, inst_new, using_db=None, update_fields=None)
        await handler(FakeModel, inst_existing, using_db=None, update_fields=None)

        assert obs.saving.await_count == 2


# ---------------------------------------------------------------------------
# delete hooks — deleting / deleted
# ---------------------------------------------------------------------------

class TestDeleteHooks:
    @pytest.mark.anyio
    async def test_deleting_called_before_delete(self):
        FakeModel, listeners = make_fake_model()
        obs = ModelObserver()
        obs.deleting = AsyncMock()
        _register_observer(FakeModel, obs)

        from tortoise.signals import Signals
        handler = listeners[Signals.pre_delete][0]
        inst = make_instance(saved_in_db=True)
        await handler(FakeModel, inst, using_db=None)

        obs.deleting.assert_awaited_once_with(inst)

    @pytest.mark.anyio
    async def test_deleted_called_after_delete(self):
        FakeModel, listeners = make_fake_model()
        obs = ModelObserver()
        obs.deleted = AsyncMock()
        _register_observer(FakeModel, obs)

        from tortoise.signals import Signals
        handler = listeners[Signals.post_delete][0]
        inst = make_instance(saved_in_db=True)
        await handler(FakeModel, inst, using_db=None)

        obs.deleted.assert_awaited_once_with(inst)


# ---------------------------------------------------------------------------
# Only defined methods are called
# ---------------------------------------------------------------------------

class TestPartialObserver:
    @pytest.mark.anyio
    async def test_undefined_hook_not_called(self):
        """Observer with only `created` should not crash when `updated` fires."""
        FakeModel, listeners = make_fake_model()

        class MinimalObs(ModelObserver):
            created = AsyncMock()

        FakeModel.observe(MinimalObs)
        from tortoise.signals import Signals
        handler = listeners[Signals.post_save][0]
        inst = make_instance()

        # updated fires — should not raise
        await handler(FakeModel, inst, created=False, using_db=None, update_fields=None)
        MinimalObs.created.assert_not_awaited()

    @pytest.mark.anyio
    async def test_only_created_fires_on_insert(self):
        FakeModel, listeners = make_fake_model()

        class MinimalObs(ModelObserver):
            created = AsyncMock()

        FakeModel.observe(MinimalObs)
        from tortoise.signals import Signals
        handler = listeners[Signals.post_save][0]
        inst = make_instance()

        await handler(FakeModel, inst, created=True, using_db=None, update_fields=None)
        MinimalObs.created.assert_awaited_once_with(inst)
