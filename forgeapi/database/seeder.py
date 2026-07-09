class Seeder:
    """Base class for database seeders.

    Subclass and implement :meth:`run` to populate the database.
    Call :meth:`execute` (not :meth:`run` directly) so that the entire seed
    runs inside an atomic database transaction — a failure mid-seed rolls
    everything back instead of leaving the database in a partial state.

    Example::

        import os
        from forgeapi.database import Seeder
        from app.models import User
        from app.utils import hash_password


        class UserSeeder(Seeder):
            async def run(self) -> None:
                # Never hardcode passwords — read from the environment instead.
                await User.get_or_create(
                    username="admin",
                    defaults={
                        "email":         "admin@example.com",
                        "password_hash": hash_password(os.environ["ADMIN_PASSWORD"]),
                        "is_active":     True,
                    },
                )
    """

    async def run(self) -> None:
        raise NotImplementedError(
            f"{self.__class__.__name__}.run() must be implemented."
        )

    async def execute(self) -> None:
        """Run the seeder inside an atomic database transaction.

        Use this method from CLI runners and test helpers.  A single
        transaction ensures that a mid-seed failure triggers a full rollback
        rather than leaving the database in a partial state.
        """
        try:
            from tortoise.transactions import in_transaction
        except ImportError:
            from forgeapi.exceptions import ForgeAPIImportError
            raise ForgeAPIImportError(
                "Seeder.execute() requires Tortoise ORM.",
                hint="pip install tortoise-orm",
            )
        async with in_transaction():
            await self.run()
