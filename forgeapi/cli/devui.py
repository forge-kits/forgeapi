"""Tabbed terminal interface of ``forgeapi runserver --dev`` (needs ``pip install forge-kits[dev]``).

One tab per process plus a ``logs`` tab for what the application and forgeapi log, or one interleaved stream.
Search, per-process restart and timestamps work in both.  The data sits in :class:`DevApp`, so
the processes themselves are driven by :class:`forgeapi.cli.multiplex.Multiplexer`.
"""
from __future__ import annotations

import asyncio
import time
from collections import deque
from dataclasses import dataclass
from typing import Any, Callable

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.content import Content
from textual.widgets import Footer, Input, RichLog, TabbedContent, TabPane

from forgeapi.cli import multiplex
from forgeapi.cli.devviews import LOGS_VIEW, view_for, views_for
from forgeapi.cli.logfmt import LEVEL_STYLES, LEVEL_WIDTH, parse_line

MAX_LINES = 5000                  # kept per view
VIEW_COLORS = ("cyan", "magenta", "yellow", "green", "blue")
STATE_DOTS = {
    multiplex.STATE_RUNNING: "green",
    multiplex.STATE_STARTING: "yellow",
    multiplex.STATE_RESTARTING: "yellow",
    multiplex.STATE_EXITED: "red",
    multiplex.STATE_FAILED: "red",
    multiplex.STATE_STOPPED: "grey50",
}

#: ``make_mux(emit, on_state)`` builds the multiplexer, so the app owns the callbacks.
MuxFactory = Callable[[multiplex.Emit, multiplex.OnState], Any]


@dataclass
class Entry:
    stamp: str
    view: str
    process: str
    level: str | None
    message: Text
    status: bool = False

    @property
    def plain(self) -> str:
        return f"{self.level or ''} {self.message.plain}"


class DevApp(App[int]):
    TITLE = "ForgeAPI"
    CSS = """
    #search { dock: bottom; display: none; }
    #search.visible { display: block; }
    #stream { display: none; }
    RichLog { padding: 0 1; }
    """
    BINDINGS = [
        Binding("tab", "next_tab", "Next tab", priority=True),
        Binding("shift+tab", "prev_tab", "Prev tab", show=False, priority=True),
        *[Binding(str(n), f"goto({n})", show=False) for n in range(1, 10)],
        Binding("r", "restart", "Restart"),
        Binding("slash", "search", "Search"),
        Binding("escape", "clear_search", "Clear", show=False),
        Binding("m", "toggle_mode", "Tabs/Stream"),
        Binding("t", "toggle_timestamps", "Time"),
        Binding("c", "clear", "Clear log"),
        Binding("q", "quit_all", "Quit"),
        Binding("ctrl+c", "quit_all", "Quit", show=False, priority=True),
    ]

    def __init__(
        self,
        make_mux: MuxFactory,
        processes: list[str],
        *,
        stream: bool = False,
        timestamps: bool = False,
    ) -> None:
        super().__init__()
        self._processes = list(processes)
        self._views = views_for(self._processes)
        self._colors = {v: VIEW_COLORS[i % len(VIEW_COLORS)] for i, v in enumerate(self._views)}
        self._lines: dict[str, deque[Entry]] = {v: deque(maxlen=MAX_LINES) for v in self._views}
        self._all: deque[Entry] = deque(maxlen=MAX_LINES * 2)
        self._states: dict[str, str] = {}
        self._stream = stream
        self._timestamps = timestamps
        self._query = ""
        self._exit_code = 0
        self._stopping = False
        self._mux = make_mux(self._on_line, self._on_state)
        self._mux_task: asyncio.Task | None = None

    # ── layout ───────────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        with TabbedContent(id="tabs"):
            for view in self._views:
                with TabPane(self._label(view), id=f"pane-{view}"):
                    yield RichLog(id=f"log-{view}", wrap=True, max_lines=MAX_LINES, markup=False, highlight=False)
        yield RichLog(id="stream", wrap=True, max_lines=MAX_LINES * 2, markup=False, highlight=False)
        yield Input(placeholder="search (Enter keeps the filter, Esc clears it)", id="search")
        yield Footer()

    def on_mount(self) -> None:
        self._apply_mode()
        self._update_subtitle()
        self.call_after_refresh(self._focus_log)
        self._mux_task = asyncio.create_task(self._run_mux(), name="devui:multiplexer")

    async def _run_mux(self) -> None:
        code = await self._mux.run()
        self._exit_code = code
        self.sub_title = f"server ended with code {code}, press q to quit"

    # ── incoming ─────────────────────────────────────────────────────────────

    def _on_line(self, process: str, line: str, kind: str) -> None:
        stamp = time.strftime("%H:%M:%S")
        if kind == "out":
            level, message, logger = parse_line(Text.from_ansi(line))
            entry = Entry(stamp, view_for(process, logger), process, level, message)
        else:
            entry = Entry(stamp, process, process, None, Text(line, style="dim italic"), status=True)
        if entry.view not in self._lines:           # a view the interface has no tab for
            entry.view = process
        self._lines[entry.view].append(entry)
        self._all.append(entry)
        if self._matches(entry):
            self._write(entry)

    def _on_state(self, process: str, state: str) -> None:
        self._states[process] = state
        if self.is_mounted:
            self._relabel(process)

    # ── rendering ────────────────────────────────────────────────────────────

    def _matches(self, entry: Entry) -> bool:
        return not self._query or self._query in entry.plain.lower()

    def _render(self, entry: Entry, *, named: bool) -> Text:
        text = Text()
        if self._timestamps:
            text.append(entry.stamp + "  ", style="dim")
        if named:
            view = entry.view
            text.append(view.ljust(max(len(v) for v in self._views)), style=f"bold {self._colors.get(view, 'white')}")
            text.append(" | ", style="dim")
        if entry.status:
            text.append(" " * LEVEL_WIDTH + "  ")
        else:
            text.append((entry.level or "").ljust(LEVEL_WIDTH), style=LEVEL_STYLES.get(entry.level or "", ""))
            text.append("  ")
        text.append_text(entry.message)
        return text

    @staticmethod
    def _append(log: RichLog, text: Text) -> None:
        # follow the output only while the reader is at the bottom: scrolling up to read must stick
        log.write(text, scroll_end=log.is_vertical_scroll_end or log.virtual_size.height == 0)

    def _write(self, entry: Entry) -> None:
        self._append(self.query_one(f"#log-{entry.view}", RichLog), self._render(entry, named=False))
        self._append(self.query_one("#stream", RichLog), self._render(entry, named=True))

    def _redraw(self) -> None:
        for view in self._views:
            log = self.query_one(f"#log-{view}", RichLog)
            log.clear()
            for entry in self._lines[view]:
                if self._matches(entry):
                    log.write(self._render(entry, named=False))
        stream = self.query_one("#stream", RichLog)
        stream.clear()
        for entry in self._all:
            if self._matches(entry):
                stream.write(self._render(entry, named=True))

    def _label(self, view: str) -> Content:
        if view in self._processes:
            color = STATE_DOTS.get(self._states.get(view, multiplex.STATE_STARTING), "yellow")
        else:
            color = "grey50"
        return Content.assemble(("● ", color), view)

    def _relabel(self, view: str) -> None:
        if view in self._views:
            self.query_one("#tabs", TabbedContent).get_tab(f"pane-{view}").label = self._label(view)

    def _update_subtitle(self) -> None:
        parts = ["stream" if self._stream else "tabs"]
        if self._timestamps:
            parts.append("timestamps")
        if self._query:
            parts.append(f'filter "{self._query}"')
        self.sub_title = " | ".join(parts)

    def _apply_mode(self) -> None:
        self.query_one("#tabs").display = not self._stream
        self.query_one("#stream").display = self._stream

    def _focus_log(self) -> None:
        """Keys such as PgUp scroll the log that is on screen, so it must be the focused one."""
        target = "#stream" if self._stream else f"#log-{self._active_view()}"
        self.query_one(target, RichLog).focus()

    def on_tabbed_content_tab_activated(self, event: TabbedContent.TabActivated) -> None:
        if not isinstance(self.focused, Input):
            self.call_after_refresh(self._focus_log)

    # ── actions ──────────────────────────────────────────────────────────────

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        if isinstance(self.focused, Input) and action in ("next_tab", "prev_tab"):
            return False
        return True

    def _step(self, delta: int) -> None:
        tabs = self.query_one("#tabs", TabbedContent)
        current = self._views.index(self._active_view())
        tabs.active = f"pane-{self._views[(current + delta) % len(self._views)]}"

    def _active_view(self) -> str:
        active = self.query_one("#tabs", TabbedContent).active
        return active.removeprefix("pane-") or self._views[0]

    def action_next_tab(self) -> None:
        if not self._stream:
            self._step(1)

    def action_prev_tab(self) -> None:
        if not self._stream:
            self._step(-1)

    def action_goto(self, number: int) -> None:
        if not self._stream and 1 <= number <= len(self._views):
            self.query_one("#tabs", TabbedContent).active = f"pane-{self._views[number - 1]}"

    def action_toggle_mode(self) -> None:
        self._stream = not self._stream
        self._apply_mode()
        self._update_subtitle()
        self.call_after_refresh(self._focus_log)

    def action_toggle_timestamps(self) -> None:
        self._timestamps = not self._timestamps
        self._redraw()
        self._update_subtitle()

    def action_clear(self) -> None:
        if self._stream:
            self._all.clear()
            for view in self._views:
                self._lines[view].clear()
        else:
            self._lines[self._active_view()].clear()
        self._redraw()

    def action_search(self) -> None:
        box = self.query_one("#search", Input)
        box.add_class("visible")
        box.focus()

    def action_clear_search(self) -> None:
        box = self.query_one("#search", Input)
        box.value = ""
        box.remove_class("visible")
        self._set_query("")
        self._focus_log()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "search":
            self._set_query(event.value)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "search":
            event.input.remove_class("visible")      # keep the filter, give the keys back
            self._focus_log()

    def _set_query(self, query: str) -> None:
        self._query = query.strip().lower()
        self._redraw()
        self._update_subtitle()

    async def action_restart(self) -> None:
        view = self._active_view() if not self._stream else "server"
        process = "server" if view == LOGS_VIEW else view
        if process not in self._processes:
            return
        self.notify(f"Restarting {process}")
        await self._mux.restart(process)

    async def action_quit_all(self) -> None:
        if self._stopping:                           # a second press: do not wait for a graceful stop
            kill = getattr(self._mux, "kill_now", None)
            if kill:
                kill()
            self.exit(self._exit_code)
            return
        self._stopping = True
        self.sub_title = "stopping, press q again to force"
        if self._mux_task is not None:
            self._mux_task.cancel()
            await asyncio.gather(self._mux_task, return_exceptions=True)
        self.exit(self._exit_code)
