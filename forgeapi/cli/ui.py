"""Terminal output for the forgeapi CLI — an artisan-style look built on ``rich``.

Colours switch off by themselves when stdout is not a terminal or ``NO_COLOR`` is set, so
piped output and CI logs stay plain text.
"""
from __future__ import annotations

import re
import time
from contextlib import contextmanager
from importlib.metadata import PackageNotFoundError, version as _pkg_version

from rich.console import Console
from rich.text import Text

console = Console(highlight=False)
err_console = Console(stderr=True, highlight=False)

BRAND = "bold #ff6a3d"

_GLYPHS = {
    "F": ["███████╗", "██╔════╝", "█████╗  ", "██╔══╝  ", "██║     ", "╚═╝     "],
    "O": [" ██████╗ ", "██╔═══██╗", "██║   ██║", "██║   ██║", "╚██████╔╝", " ╚═════╝ "],
    "R": ["██████╗ ", "██╔══██╗", "██████╔╝", "██╔══██╗", "██║  ██║", "╚═╝  ╚═╝"],
    "G": [" ██████╗ ", "██╔════╝ ", "██║  ███╗", "██║   ██║", "╚██████╔╝", " ╚═════╝ "],
    "E": ["███████╗", "██╔════╝", "█████╗  ", "██╔══╝  ", "███████╗", "╚══════╝"],
}

_BADGES = {
    "info": ("INFO", "bold white on blue"),
    "warn": ("WARN", "bold black on yellow"),
    "error": ("ERROR", "bold white on red"),
    "done": ("DONE", "bold white on green"),
    "ok": ("OK", "bold white on green"),
    "fail": ("FAIL", "bold white on red"),
}


def package_version() -> str:
    try:
        return _pkg_version("forge-kits")
    except PackageNotFoundError:
        return "dev"


def logo() -> None:
    rows = ["".join(_GLYPHS[ch][i] for ch in "FORGE") for i in range(6)]
    console.print()
    for row in rows:
        console.print(Text("  " + row, style=BRAND))
    console.print()


def blank() -> None:
    console.print()


def _badge(kind: str, label: str | None = None) -> Text:
    default_label, style = _BADGES[kind]
    return Text(f" {label or default_label} ", style=style)


def _line(kind: str, message: str, *, stderr: bool = False) -> None:
    out = err_console if stderr else console
    out.print(Text.assemble("  ", _badge(kind), "  ", message), soft_wrap=True)


def info(message: str) -> None:
    _line("info", message)


def warn(message: str, *, stderr: bool = False) -> None:
    _line("warn", message, stderr=stderr)


def success(message: str) -> None:
    _line("done", message)


def error(message: str, hint: str = "") -> None:
    _line("error", message, stderr=True)
    if hint:
        err_console.print(Text.assemble("\n  ", (hint, "dim")), soft_wrap=True)


def leader(left: str, status: str, *, kind: str = "done", detail: str = "") -> None:
    """``  name ............ 12ms DONE`` — dotted line from *left* to a status badge."""
    badge = _badge(kind, status)
    tail = f"{detail} " if detail else ""
    used = 2 + len(left) + 1 + 1 + len(tail) + len(badge.plain) + 2
    dots = "." * max(3, console.width - used)
    console.print(Text.assemble("  ", left, " ", (dots, "dim"), " ", (tail, "dim"), badge), soft_wrap=True)


def dotted(left: Text | str, right: str, *, right_style: str = "dim") -> None:
    """``  left ............ right`` — dotted line between two texts, no badge."""
    left = Text(left) if isinstance(left, str) else left
    used = 2 + len(left.plain) + 1 + 1 + len(right) + 2
    dots = "." * max(3, console.width - used)
    console.print(Text.assemble("  ", left, " ", (dots, "dim"), " ", (right, right_style)), soft_wrap=True)


@contextmanager
def task(label: str):
    """Run a block, then print ``label ..... 12ms DONE`` (or ``FAIL`` and re-raise)."""
    start = time.perf_counter()
    try:
        yield
    except Exception:
        leader(label, "FAIL", kind="error", detail=f"{int((time.perf_counter() - start) * 1000)}ms")
        raise
    leader(label, "DONE", detail=f"{int((time.perf_counter() - start) * 1000)}ms")


_METHOD_STYLES = {"GET": "green", "POST": "yellow", "PUT": "blue", "PATCH": "cyan", "DELETE": "red"}


def route(method: str, path: str, handler: str, method_width: int) -> None:
    """``  GET     /api/users ........ UserController.index``"""
    left = Text.assemble((method.ljust(method_width), f"bold {_METHOD_STYLES.get(method, 'white')}"), "  ", path)
    dotted(left, handler)


def check(level: str, title: str, hint: str = "") -> None:
    """One ``doctor`` result: ``level`` is ``ok``, ``warn`` or ``fail``."""
    console.print(Text.assemble("  ", _badge(level, _BADGES[level][0].center(4)), "  ", title), soft_wrap=True)
    if hint and level != "ok":
        console.print(Text.assemble("          ", (f"→ {hint}", "dim")), soft_wrap=True)


def table(columns: list[str], rows: list[list[str | Text]]) -> None:
    from rich import box
    from rich.padding import Padding
    from rich.table import Table

    grid = Table(box=box.SIMPLE_HEAD, header_style="bold yellow", pad_edge=False, padding=(0, 1))
    for column in columns:
        grid.add_column(column, overflow="fold")
    for row in rows:
        grid.add_row(*[Text(cell) if isinstance(cell, str) else cell for cell in row])
    console.print(Padding(grid, (0, 0, 0, 2)))


def indented(text: str, *, style: str = "dim", by: int = 4, wrap: bool = True) -> None:
    """Indented text. ``wrap=False`` keeps one line (paths) and lets the terminal wrap it."""
    from rich.padding import Padding

    if not wrap:
        console.print(Text(" " * by + text, style=style), soft_wrap=True)
        return
    console.print(Padding(Text(text, style=style), (0, 0, 0, by)))


def server_started(app: str, host: str, port: int, reload: bool) -> None:
    blank()
    console.print(Text.assemble("  ", ("ForgeAPI", BRAND), f" {package_version()}  ", ("development server", "dim")))
    blank()
    info(f"Server running on [http://{host}:{port}].")
    summary([("App", app), ("Reload", "on" if reload else "off")])
    blank()
    console.print(Text("  Press Ctrl+C to stop the server.", style="dim"))
    blank()


_FILE_STYLES = {"created": "green", "updated": "cyan", "exists": "yellow", "next": "magenta"}


def file_event(action: str, path: str, note: str = "") -> None:
    """``  created  app/controllers/user_controller.py`` — one line per generated file."""
    text = Text.assemble(
        "  ",
        (action.ljust(8), _FILE_STYLES.get(action, "white")),
        " ",
        path,
    )
    if note:
        text.append(f"  {note}", style="dim")
    console.print(text, soft_wrap=True)


def render_commands(groups: list[tuple[str, list[tuple[str, str]]]]) -> None:
    """Print command groups: group title, then ``usage   description`` rows."""
    width = max(len(usage) for _, rows in groups for usage, _ in rows)
    for title, rows in groups:
        if title:
            console.print(Text(f" {title}", style="bold yellow"))
        for usage, description in rows:
            name, _, args = usage.partition(" ")
            cell = Text.assemble("  ", (name, "green"), (f" {args}" if args else "", "dim"))
            cell.pad_right(width - len(usage))
            console.print(Text.assemble(cell, "  ", description))


def choose(question: str, options: list[tuple[str, str, str]], default: int = 1) -> str:
    """Numbered single choice. *options* are ``(key, label, description)``; returns the key.

    Accepts the number or the key itself; re-asks on anything else.
    """
    import typer

    width = max(len(label) for _, label, _ in options)
    console.print(Text(f" {question}", style="bold yellow"))
    for i, (_, label, description) in enumerate(options, 1):
        console.print(Text.assemble(
            "  ", (f"[{i}]", "green"), " ", (label.ljust(width), "bold"), "  ", (description, "dim"),
        ))
    accepted = {str(i): key for i, (key, _, _) in enumerate(options, 1)}
    accepted.update({key: key for key, _, _ in options})
    while True:
        raw = typer.prompt("  Choose", default=str(default))
        key = accepted.get(raw.strip().lower())
        if key:
            return key
        error(f"Enter a number from 1 to {len(options)}.")


def summary(rows: list[tuple[str, str]]) -> None:
    """``  Auth ........ cookie`` — aligned key/value lines."""
    width = max(len(k) for k, _ in rows)
    for key, value in rows:
        console.print(Text.assemble("  ", (key.ljust(width), "dim"), "  ", (value, "bold")))


def next_steps(title: str, steps: list[str]) -> None:
    from rich.panel import Panel

    body = Text()
    for i, step in enumerate(steps):
        body.append("$ ", style="dim")
        body.append(step, style="green")
        if i < len(steps) - 1:
            body.append("\n")
    console.print(Panel(body, title=title, title_align="left", border_style=BRAND, padding=(1, 2), expand=False))


_COMMENT = re.compile(r"\s+# ")
_ROW = re.compile(r"^(\S.*?)(\s{2,})(\S.*)$")


def _help_line(raw: str) -> Text:
    """Style one line of a command's ``help_text`` (see :func:`render_help`)."""
    body = raw.strip()
    if not body:
        return Text("")
    indent = len(raw) - len(raw.lstrip())
    pad = " " * indent

    if indent == 0:
        if body.startswith("Usage:"):
            line = Text.assemble((" Usage:", "bold yellow"), body[len("Usage:"):])
            line.highlight_regex(r"forgeapi", "dim")
            line.highlight_regex(r"(?<=forgeapi )\S+", "green")
            return line
        if body.endswith(":"):
            return Text(f" {body}", style="bold yellow")
        return Text(f" {body}")

    if body.startswith("#"):
        return Text(raw, style="dim")

    def with_comment(text: str, style: str) -> Text:
        match = _COMMENT.search(text)
        if not match:
            return Text(text, style=style)
        return Text.assemble((text[: match.start()], style), (text[match.start():], "dim"))

    if body.startswith("forgeapi "):
        return Text.assemble(pad, with_comment(body, "green"))
    if body.startswith("."):
        line = Text(raw)
        line.highlight_regex(r"\.\w+\([^)]*\)", "green")
        return line
    row = _ROW.match(body)
    if row and not row.group(1).split(" ", 1)[0].endswith(":"):
        left, gap, desc = row.groups()
        return Text.assemble(pad, (left, "green"), gap, with_comment(desc, ""))
    return Text(raw)


def render_help(text: str) -> None:
    """Print a command's ``help_text`` styled like the command list."""
    blank()
    for raw in text.rstrip("\n").split("\n"):
        console.print(_help_line(raw), soft_wrap=True)
    blank()
