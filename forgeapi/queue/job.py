from __future__ import annotations

import importlib


class Job:
    """Base class for all queue jobs.

    Subclass and implement ``handle()``::

        class SendWelcomeEmail(Job):
            def __init__(self, user_id: int):
                self.user_id = user_id

            async def handle(self) -> None:
                user = await User.get(id=self.user_id)
                await mailer.send(user.email, "Welcome!")

    Dispatch::

        from forgeapi.queue import dispatch
        await dispatch(SendWelcomeEmail(user_id=user.id))
        await dispatch(SendWelcomeEmail(user_id=user.id), delay=60)
    """

    queue: str = "default"
    max_tries: int = 3

    async def handle(self) -> None:
        raise NotImplementedError(f"{type(self).__name__} must implement handle()")

    def serialize(self) -> dict:
        cls = type(self)
        return {
            "class": f"{cls.__module__}.{cls.__qualname__}",
            "data": self.__dict__.copy(),
        }

    @staticmethod
    def deserialize(payload: dict) -> "Job":
        class_path = payload["class"]
        module_path, class_name = class_path.rsplit(".", 1)
        module = importlib.import_module(module_path)
        klass = getattr(module, class_name)
        job = object.__new__(klass)
        job.__dict__.update(payload.get("data", {}))
        return job
