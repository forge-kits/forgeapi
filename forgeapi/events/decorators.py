from typing import Awaitable, Callable, Type, TypeVar

from .bus import EventBus
from .event import Event

E = TypeVar("E", bound=Event)


def listen(event_class: Type[E]) -> Callable[[Callable[[E], Awaitable[None]]], Callable[[E], Awaitable[None]]]:
    """Register an async function as a listener for *event_class*.

    The decorated function is added to the global :class:`~forgeapi.events.bus.EventBus`
    immediately at import time.  All listeners for the same event class run in
    parallel via ``asyncio.gather`` when the event is dispatched.

    Args:
        event_class: The :class:`~forgeapi.events.event.Event` subclass to
            subscribe to.

    Returns:
        The original function, unchanged (pass-through decorator).

    Example — single listener::

        @listen(UserRegistered)
        async def send_welcome_email(event: UserRegistered) -> None:
            await mailer.send(event.user.email, subject="Welcome!")

    Example — multiple listeners for the same event (run in parallel)::

        @listen(UserRegistered)
        async def send_welcome_email(event: UserRegistered) -> None:
            await mailer.send(event.user.email)

        @listen(UserRegistered)
        async def create_default_settings(event: UserRegistered) -> None:
            await Settings.create(user=event.user)

    Example — background event listener::

        class UserLoggedIn(Event):
            background = True   # fire-and-forget

        @listen(UserLoggedIn)
        async def update_last_seen(event: UserLoggedIn) -> None:
            await User.filter(id=event.user_id).update(last_seen=now())
    """

    def decorator(func: Callable[[E], Awaitable[None]]) -> Callable[[E], Awaitable[None]]:
        EventBus.get_instance().register(event_class, func)
        return func

    return decorator
