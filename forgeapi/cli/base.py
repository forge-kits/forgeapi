from __future__ import annotations


class Command:
    """Base class for all CLI commands."""

    name: str = ""
    aliases: tuple[str, ...] = ()
    #: One line shown next to the command in the ``forgeapi`` listing (project commands).
    description: str = ""
    #: Commands that read or write project files must run inside a project (see main.py).
    requires_project: bool = True
    #: A group (``make``, ``db``...) typed bare only prints its help, so it needs no project.
    is_group: bool = False

    def needs_project(self, cmd: str) -> bool:
        return self.requires_project and not (self.is_group and ":" not in cmd)

    def handle(self, cmd: str, args: list[str]) -> None:
        """Entry point with the raw command line.

        A project command usually defines ``run`` instead: its typed parameters become the
        arguments and options, see :mod:`forgeapi.cli.arguments`.  ``async def run`` is awaited.
        """
        run = getattr(self, "run", None)
        if not callable(run):
            raise NotImplementedError

        import asyncio
        import inspect

        import typer

        from forgeapi.cli import ui
        from forgeapi.cli.arguments import ArgumentError, bind

        try:
            values, kwargs = bind(run, args)
        except ArgumentError as exc:
            ui.error(str(exc), hint=f"forgeapi {cmd} -h")
            raise typer.Exit(code=1)
        result = run(*values, **kwargs)
        if inspect.iscoroutine(result):
            asyncio.run(result)

    def show_help(self, cmd: str = "") -> None:
        from forgeapi.cli import ui

        text = getattr(self, "help_text", "")
        if not text and callable(getattr(self, "run", None)):
            from forgeapi.cli.arguments import help_text

            text = help_text(self.run, cmd or self.name, self.description)
        ui.render_help(text)

    def abort(self, msg: str) -> None:
        import typer

        from forgeapi.cli import ui

        ui.error(msg)
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
