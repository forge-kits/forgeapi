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
