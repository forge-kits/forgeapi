class Seeder:
    """Base class for database seeders.

    Subclass and implement :meth:`run` to populate the database.

    Example::

        from forgeapi.database import Seeder
        from app.models import User
        from app.utils import hash_password


        class UserSeeder(Seeder):
            async def run(self) -> None:
                await User.get_or_create(
                    username="admin",
                    defaults={
                        "email":         "admin@example.com",
                        "password_hash": hash_password("admin123"),
                        "is_active":     True,
                    },
                )
    """

    async def run(self) -> None:
        raise NotImplementedError
