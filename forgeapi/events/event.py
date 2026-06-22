from typing import ClassVar


class Event:
    """Base class for all application events.

    Subclass this to define your own events.  Override ``background = True``
    to make the event non-blocking (fire-and-forget via ``asyncio.create_task``).

    Attributes:
        background: When ``True``, :meth:`dispatch` schedules listeners as a
            background task and returns immediately without awaiting them.
            Defaults to ``False``.

    Example — synchronous event (blocks until all listeners finish)::

        class OrderCreated(Event):
            def __init__(self, order_id: int, total: float) -> None:
                self.order_id = order_id
                self.total = total

        @listen(OrderCreated)
        async def send_confirmation(event: OrderCreated):
            await email.send(f"Order #{event.order_id} confirmed, total: {event.total}")

        # inside a route
        await OrderCreated(order_id=42, total=99.90).dispatch()

    Example — background event (does NOT block the HTTP response)::

        class UserLoggedIn(Event):
            background = True

            def __init__(self, user_id: int) -> None:
                self.user_id = user_id

        @listen(UserLoggedIn)
        async def update_last_seen(event: UserLoggedIn):
            await User.filter(id=event.user_id).update(last_seen=now())

        # route returns instantly; listener runs in the background
        await UserLoggedIn(user_id=user.id).dispatch()
    """

    background: ClassVar[bool] = False

    async def dispatch(self) -> None:
        """Fire this event.

        Looks up all registered listeners for this event type in the global
        :class:`~forgeapi.events.bus.EventBus` and executes them via
        ``asyncio.gather``.

        * ``background = False`` (default) — awaits all listeners before
          returning.  Any listener exceptions are logged but do **not**
          propagate.
        * ``background = True`` — schedules listeners as an
          ``asyncio.create_task`` and returns immediately.
        """
        from .bus import EventBus
        await EventBus.get_instance().dispatch(self)
