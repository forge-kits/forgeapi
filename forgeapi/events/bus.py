import asyncio
import importlib.util
import logging
import sys
from pathlib import Path
from typing import Callable

logger = logging.getLogger("forgeapi.events")


class EventBus:
    """Central event dispatcher — singleton registry of event → listeners.

    You rarely need to interact with ``EventBus`` directly.  Use the
    :func:`~forgeapi.events.decorators.listen` decorator to register
    listeners and :meth:`~forgeapi.events.event.Event.dispatch` to fire
    events.

    The singleton is created on first access via :meth:`get_instance`.  Call
    :meth:`reset` between test cases to start with an empty registry.

    Example — manual registration (without the decorator)::

        bus = EventBus.get_instance()
        bus.register(OrderCreated, my_async_handler)

    Example — loading all listeners from a directory::

        bus = EventBus.get_instance()
        bus.load_from_dir("app/listeners")
    """

    _instance: "EventBus | None" = None

    def __init__(self) -> None:
        self._listeners: dict[type, list[Callable]] = {}

    @classmethod
    def get_instance(cls) -> "EventBus":
        """Return the process-wide singleton instance.

        Returns:
            The single :class:`EventBus` instance, created on first call.
        """
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Destroy the singleton and clear all registered listeners.

        Intended for use in tests so each test case starts with a clean slate::

            @pytest.fixture(autouse=True)
            def reset_bus():
                EventBus.reset()
                yield
                EventBus.reset()
        """
        cls._instance = None

    def register(self, event_class: type, listener: Callable) -> None:
        """Register *listener* to be called when *event_class* is dispatched.

        Args:
            event_class: The :class:`~forgeapi.events.event.Event` subclass
                to listen for.
            listener: An ``async def`` function that accepts a single argument
                of type *event_class*.

        Example::

            async def my_handler(event: OrderCreated) -> None:
                await email.send(...)

            EventBus.get_instance().register(OrderCreated, my_handler)
        """
        self._listeners.setdefault(event_class, []).append(listener)

    def listeners_for(self, event_class: type) -> list[Callable]:
        """Return all listeners registered for *event_class*.

        Args:
            event_class: An :class:`~forgeapi.events.event.Event` subclass.

        Returns:
            List of callables (may be empty).
        """
        return self._listeners.get(event_class, [])

    async def dispatch(self, event: "Event") -> None:  # noqa: F821
        """Fire *event* and invoke all registered listeners.

        Behaviour depends on ``event.background``:

        * ``False`` (default): awaits ``asyncio.gather`` over all listeners.
          Individual listener exceptions are logged but **not** re-raised.
        * ``True``: wraps execution in ``asyncio.create_task`` and returns
          immediately.

        Args:
            event: An :class:`~forgeapi.events.event.Event` instance.
        """
        listeners = self.listeners_for(type(event))
        if not listeners:
            return

        if event.background:
            asyncio.create_task(
                self._run_all(event, listeners),
                name=f"event:{type(event).__name__}",
            )
        else:
            await self._run_all(event, listeners)

    async def _run_all(self, event: "Event", listeners: list[Callable]) -> None:  # noqa: F821
        results = await asyncio.gather(
            *(listener(event) for listener in listeners),
            return_exceptions=True,
        )
        for listener, result in zip(listeners, results):
            if isinstance(result, Exception):
                logger.error(
                    "Listener '%s' failed for event '%s': %s",
                    listener.__name__,
                    type(event).__name__,
                    result,
                    exc_info=result,
                )

    def load_from_dir(self, directory: str) -> None:
        """Import all ``*.py`` files from *directory* to auto-register listeners.

        Each file is imported as an isolated module.  Any ``@listen(...)``
        decorators at module level execute on import and register their
        functions with this bus.  Files starting with ``_`` are skipped.
        Already-imported files (by path) are skipped on subsequent calls.

        Args:
            directory: Relative or absolute path to the listeners directory
                (e.g. ``"app/listeners"``).

        Example::

            # app/listeners/user_listeners.py
            from forgeapi.events import listen
            from app.events import UserRegistered

            @listen(UserRegistered)
            async def send_welcome_email(event: UserRegistered):
                await mailer.send_welcome(event.user.email)

            # main.py
            bus = EventBus.get_instance()
            bus.load_from_dir("app/listeners")
        """
        dir_path = Path(directory)
        if not dir_path.exists():
            logger.warning("Listeners directory not found: '%s'", directory)
            return

        for py_file in sorted(dir_path.glob("*.py")):
            if py_file.name.startswith("_"):
                continue
            self._import_file(py_file)

    def _import_file(self, path: Path) -> None:
        module_name = f"_fk_listener_{path.stem}"
        if module_name in sys.modules:
            return

        spec = importlib.util.spec_from_file_location(module_name, path)
        if not spec or not spec.loader:
            logger.warning("Cannot load listener file: %s", path)
            return

        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        try:
            spec.loader.exec_module(module)
            logger.debug("Loaded listeners from '%s'", path)
        except Exception as exc:
            del sys.modules[module_name]
            logger.error("Failed to load listener file '%s': %s", path, exc, exc_info=exc)
