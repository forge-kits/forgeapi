"""Uniform look for the output of the processes in `runserver --dev`."""
import io

import pytest
from rich.console import Console
from rich.text import Text

from forgeapi.cli import ui
from forgeapi.cli.logfmt import LEVEL_WIDTH, parse_line


def _parse(line: str):
    level, message, _ = parse_line(Text.from_ansi(line))
    return level, message.plain


@pytest.mark.parametrize("line,level,message", [
    ("INFO:     Application startup complete.", "INFO", "Application startup complete."),
    ("\x1b[32mINFO\x1b[0m:     Started server process [1]", "INFO", "Started server process [1]"),
    ("WARNING:  StatReload detected changes", "WARNING", "StatReload detected changes"),
    ("   INFO   Queue worker started on 'default'.", "INFO", "Queue worker started on 'default'."),
    ("   WARN   something odd", "WARNING", "something odd"),
    ("   DONE   Done.", "DONE", "Done."),
    ("   ERROR   Cannot connect to the database", "ERROR", "Cannot connect to the database"),
    ("2026-11-17 16:33:47  DEBUG  forgeapi.cache.provider  Cache: driver=database",
     "DEBUG", "forgeapi.cache.provider  Cache: driver=database"),
    ("2026-11-17 16:34:29  INFO  forgeapi.access  GET /send → 200 [2.2ms]", "INFO", "forgeapi.access  GET /send → 200 [2.2ms]"),
])
def test_parse_known_formats(line, level, message):
    assert _parse(line) == (level, message)


@pytest.mark.parametrize("line", [
    "JOB RAN in the queue worker",
    "Mail driver is 'log': messages are written to the log and NOT sent.",
    "INFORMATION is not a level",
    "",
])
def test_unknown_lines_have_no_level(line):
    level, message = _parse(line)
    assert level is None and message == line


def test_colours_of_the_message_survive():
    level, message, _ = parse_line(Text.from_ansi('INFO:     "GET / HTTP/1.1" \x1b[32m200 OK\x1b[0m'))
    assert level == "INFO" and message.plain == '"GET / HTTP/1.1" 200 OK'
    assert any(span.style for span in message.spans)


def test_printer_aligns_every_source(monkeypatch):
    buf = io.StringIO()
    monkeypatch.setattr(ui, "console", Console(file=buf, width=100, color_system=None, highlight=False))
    emit = ui.process_printer(["server", "queue", "schedule"])
    emit("server", "INFO:     Application startup complete.", "out")
    emit("queue", "   INFO   Queue worker started on 'default'.", "out")
    emit("schedule", "2026-11-17 16:36:06  WARNING  forgeapi.x  careful", "out")
    emit("queue", "plain output", "out")
    emit("queue", "stopped", "status")
    rows = buf.getvalue().splitlines()
    w = LEVEL_WIDTH

    def row(name, level, text):
        return f"  {name} | {level.ljust(w)}  {text}"

    assert rows[0] == row("server  ", "INFO", "Application startup complete.")
    assert rows[1] == row("queue   ", "INFO", "Queue worker started on 'default'.")
    assert rows[2] == row("schedule", "WARNING", "forgeapi.x  careful")
    assert rows[3] == row("queue   ", "", "plain output")
    assert rows[4] == row("queue   ", "", "stopped")


def test_server_logger_lines_go_to_the_logs_view(monkeypatch):
    buf = io.StringIO()
    monkeypatch.setattr(ui, "console", Console(file=buf, width=120, color_system=None, highlight=False))
    emit = ui.process_printer(["server", "queue"])
    emit("server", "INFO:     Application startup complete.", "out")
    emit("server", "2026-11-17 16:36:06  INFO  forgeapi.access  GET /ping -> 200", "out")
    emit("server", "2026-11-17 16:36:07  INFO  forgeapi.broadcasting.provider  connected", "out")
    emit("server", "2026-11-17 16:36:08  WARNING  app.orders  stock is low", "out")
    emit("queue", "2026-11-17 16:36:09  INFO  forgeapi.queue  job done", "out")
    rows = [r.split("|")[0].strip() for r in buf.getvalue().splitlines()]
    assert rows == ["server", "server", "logs", "logs", "queue"]


def test_timestamps_option(monkeypatch):
    import re

    buf = io.StringIO()
    monkeypatch.setattr(ui, "console", Console(file=buf, width=100, color_system=None, highlight=False))
    ui.process_printer(["server"], timestamps=True)("server", "INFO:     up", "out")
    assert re.match(r"  \d\d:\d\d:\d\d  server", buf.getvalue())
