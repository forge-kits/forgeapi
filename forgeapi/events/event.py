import logging
import uuid
from typing import Any, ClassVar

logger = logging.getLogger("forgeapi.events")


class Event:
    """Base class for all application events.

    Subclass this to define your own events.  Override class variables to
    control dispatch behaviour:

    * ``background`` — fire-and-forget via ``asyncio.create_task`` (default ``False``).
    * ``redis`` — publish to Redis pub/sub so all workers receive the event
      (default ``False``).  Requires :meth:`~forgeapi.events.bus.EventBus.set_redis`
      to be called before dispatch.
    * ``ttl`` — deduplication window in seconds.  When set, the first worker
      that acquires the Redis lock processes the event; others skip it.
      Only meaningful when ``redis = True``.

    Every instance automatically gets a unique ``event_id`` (UUID4) on
    creation.  This ID is preserved through Redis serialisation so the same
    event is never processed twice within the ``ttl`` window.

    Example — local background event (unchanged from before)::

        class UserLoggedIn(Event):
            background = True

            def __init__(self, user_id: int) -> None:
                self.user_id = user_id

    Example — Redis event with deduplication::

        class OrderShipped(Event):
            redis = True
            ttl = 300  # skip if same event_id seen within 5 minutes

            def __init__(self, order_id: int) -> None:
                self.order_id = order_id

        # inside a route — unchanged call
        await OrderShipped(order_id=42).dispatch()

    Serialisation:
        Override :meth:`to_dict` / :meth:`from_dict` if your event holds
        non-JSON-serialisable objects.  By default ``to_dict`` dumps all
        instance ``__dict__`` attributes; ``from_dict`` restores them.
    """

    _registry: ClassVar[dict[str, type["Event"]]] = {}

    background: ClassVar[bool] = False
    redis: ClassVar[bool] = False
    redis_type: ClassVar[str] = "pubsub"   # "pubsub" | "stream"
    namespace: ClassVar[str] = "forgeapi:events"
    ttl: ClassVar[int | None] = None

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        name = cls.__name__
        if name in Event._registry and Event._registry[name] is not cls:
            logger.warning(
                "Event class name %r is already registered by %r; overwriting with %r. "
                "Use unique class names to avoid serialisation collisions.",
                name,
                Event._registry[name],
                cls,
            )
        Event._registry[name] = cls

    def __new__(cls, *args: Any, **kwargs: Any) -> "Event":
        instance = super().__new__(cls)
        instance.event_id = str(uuid.uuid4())
        return instance

    async def dispatch(self) -> None:
        """Fire this event via the global :class:`~forgeapi.events.bus.EventBus`.

        * If ``redis = True`` and Redis is configured — publishes to the Redis
          channel; local listeners are invoked by the subscriber worker.
        * Otherwise — runs all local listeners directly (existing behaviour).
        """
        from .bus import EventBus
        await EventBus.get_instance().dispatch(self)

    def to_dict(self) -> dict[str, Any]:
        """Serialise this event to a plain dict for Redis transport.

        The ``_event_type`` key is added automatically and is used by
        :meth:`from_dict` to reconstruct the correct subclass.
        """
        return {"_event_type": type(self).__name__, **self.__dict__}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Event":
        """Reconstruct an event from a serialised dict.

        Args:
            data: Dict produced by :meth:`to_dict` (must contain ``_event_type``).

        Returns:
            The concrete :class:`Event` subclass instance.

        Raises:
            ValueError: If ``_event_type`` is missing or the type is not registered.
        """
        data = dict(data)
        event_type = data.get("_event_type")
        if not event_type:
            raise ValueError(f"Event dict missing '_event_type' key: {data!r}")
        klass = cls._registry.get(event_type)
        if klass is None:
            raise ValueError(
                f"Unknown event type {event_type!r}. "
                "Ensure the module defining it is imported before deserialising."
            )
        data.pop("_event_type")
        instance = klass.__new__(klass)
        instance.__dict__.update(data)
        return instance
