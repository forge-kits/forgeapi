from __future__ import annotations


class Command:
    """Base class for all CLI commands."""

    name: str = ""
    aliases: tuple[str, ...] = ()

    def handle(self, cmd: str, args: list[str]) -> None:
        raise NotImplementedError

    def show_help(self, cmd: str = "") -> None:
        import typer
        typer.echo(getattr(self, "help_text", ""))

    def abort(self, msg: str) -> None:
        import typer
        typer.echo(f"Error: {msg}", err=True)
        raise typer.Exit(code=1)

    @staticmethod
    async def connect_database(tortoise_config: dict) -> None:
        """Initialise Tortoise and create missing tables, with readable errors.

        Raises :class:`~forgeapi.exceptions.ForgeAPIError` (the original error is chained) so a
        command's ``handle`` can turn it into a one-line message instead of a traceback.
        """
        from tortoise import Tortoise

        from forgeapi.exceptions import ForgeAPIError

        alias = next(iter(tortoise_config.get("connections", {"default": None})))
        try:
            await Tortoise.init(config=tortoise_config)
            # some drivers (sqlite) connect lazily: force a real connection here so that a
            # connection problem is always reported as such, not as a table-creation error
            await Tortoise.get_connection(alias).execute_query("SELECT 1")
        except Exception as exc:
            try:
                await Tortoise.close_connections()
            except Exception:
                pass
            raise ForgeAPIError(
                f"Cannot connect to the database: {exc}",
                hint="check DB_* in .env and that the database server is running (forgeapi doctor)",
            ) from exc
        try:
            await Tortoise.generate_schemas(safe=True)
        except Exception as exc:
            await Tortoise.close_connections()
            raise ForgeAPIError(
                f"Cannot create the database tables: {exc}",
                hint="check that the database user may create tables (forgeapi doctor)",
            ) from exc
