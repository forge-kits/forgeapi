"""The tabbed interface of the dev `runserver`, driven headless with a fake multiplexer."""
import asyncio

import pytest

pytest.importorskip("textual")

from textual.widgets import Input, RichLog, TabbedContent  # noqa: E402

from forgeapi.cli.devui import DevApp  # noqa: E402

SERVER = "INFO:     Application startup complete."
BROADCAST = "2026-11-17 16:36:07  INFO  forgeapi.broadcasting.provider  connected"
ACCESS = "2026-11-17 16:36:06  INFO  forgeapi.access  GET /ping -> 200"
QUEUE = "   INFO   Queue worker started on 'default'."


class FakeMux:
    def __init__(self, emit, on_state):
        self.emit, self.on_state = emit, on_state
        self.restarted: list[str] = []
        self.killed = False
        self.cancelled = False

    async def run(self) -> int:
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.cancelled = True
            raise

    async def restart(self, name: str) -> None:
        self.restarted.append(name)

    def kill_now(self) -> None:
        self.killed = True


def make_app(**kw):
    holder = {}

    def factory(emit, on_state):
        holder["mux"] = FakeMux(emit, on_state)
        return holder["mux"]

    app = DevApp(factory, ["server", "queue", "schedule"], **kw)
    return app, holder


def texts(app: DevApp, view: str) -> list[str]:
    return [strip.text.rstrip() for strip in app.query_one(f"#log-{view}", RichLog).lines]


def stream_texts(app: DevApp) -> list[str]:
    return [strip.text.rstrip() for strip in app.query_one("#stream", RichLog).lines]


async def feed(app, holder, *lines):
    for process, line in lines:
        holder["mux"].emit(process, line, "out")
    await asyncio.sleep(0)


async def test_one_tab_per_process_plus_logs():
    app, _ = make_app()
    async with app.run_test(size=(120, 30)) as pilot:
        await pilot.pause()
        tabs = app.query_one("#tabs", TabbedContent)
        assert [t.id for t in tabs.query("TabPane")] == ["pane-server", "pane-queue", "pane-schedule", "pane-logs"]
        assert tabs.active == "pane-server"


async def test_the_visible_log_has_the_focus_so_keys_scroll_it():
    app, holder = make_app()
    async with app.run_test(size=(120, 12)) as pilot:
        await pilot.pause()
        assert app.focused.id == "log-server"
        await pilot.press("tab")
        await pilot.pause()
        assert app.focused.id == "log-queue"
        await pilot.press("m")                        # stream mode
        await pilot.pause()
        assert app.focused.id == "stream"
        await pilot.press("m")
        await pilot.pause()
        assert app.focused.id == "log-queue"


async def test_page_up_scrolls_the_visible_tab():
    app, holder = make_app()
    async with app.run_test(size=(120, 12)) as pilot:
        await pilot.pause()
        for i in range(80):
            holder["mux"].emit("server", f"INFO:     line {i}", "out")
        await pilot.pause()
        log = app.query_one("#log-server", RichLog)
        end = log.scroll_y
        await pilot.press("pageup")
        await pilot.pause()
        assert log.scroll_y < end
        up = log.scroll_y
        await pilot.press("down")
        await pilot.pause()
        assert log.scroll_y > up                      # arrows scroll too


async def test_lines_go_to_their_own_tab():
    app, holder = make_app()
    async with app.run_test(size=(120, 30)) as pilot:
        await pilot.pause()
        await feed(app, holder, ("server", SERVER), ("server", ACCESS), ("server", BROADCAST), ("queue", QUEUE))
        await pilot.pause()
        assert any("Application startup complete." in t for t in texts(app, "server"))
        assert any("GET /ping" in t for t in texts(app, "server"))          # HTTP stays with the server
        assert not any("broadcasting" in t for t in texts(app, "server"))
        assert any("forgeapi.broadcasting.provider" in e.message.plain for e in app._lines["logs"])
        assert [e.plain for e in app._lines["queue"]] == ["INFO Queue worker started on 'default'."]


async def test_switching_tabs_with_keys():
    app, _ = make_app()
    async with app.run_test(size=(120, 30)) as pilot:
        await pilot.pause()
        tabs = app.query_one("#tabs", TabbedContent)
        await pilot.press("tab")
        assert tabs.active == "pane-queue"
        await pilot.press("3")
        assert tabs.active == "pane-schedule"
        await pilot.press("shift+tab")
        assert tabs.active == "pane-queue"
        await pilot.press("4")
        assert tabs.active == "pane-logs"
        await pilot.press("tab")
        assert tabs.active == "pane-server"          # wraps around


async def test_search_filters_and_escape_restores():
    app, holder = make_app()
    async with app.run_test(size=(120, 30)) as pilot:
        await pilot.pause()
        await feed(app, holder, ("server", "INFO:     alpha one"), ("server", "INFO:     beta two"), ("server", "INFO:     alpha three"))
        await pilot.pause()
        assert len(texts(app, "server")) == 3

        await pilot.press("slash")
        await pilot.press(*"alpha")
        await pilot.pause()
        assert [t for t in texts(app, "server")] and all("alpha" in t for t in texts(app, "server"))
        assert len(texts(app, "server")) == 2
        assert "alpha" in app.sub_title

        await feed(app, holder, ("server", "INFO:     beta again"), ("server", "INFO:     alpha four"))
        await pilot.pause()
        assert len(texts(app, "server")) == 3        # new lines are filtered too

        await pilot.press("escape")
        await pilot.pause()
        assert len(texts(app, "server")) == 5
        assert app._query == ""


async def test_enter_keeps_the_filter_and_gives_keys_back():
    app, holder = make_app()
    async with app.run_test(size=(120, 30)) as pilot:
        await pilot.pause()
        await feed(app, holder, ("server", "INFO:     alpha"), ("server", "INFO:     beta"))
        await pilot.press("slash")
        await pilot.press(*"beta")
        await pilot.press("enter")
        await pilot.pause()
        assert not isinstance(app.focused, Input)
        assert len(texts(app, "server")) == 1
        await pilot.press("tab")                     # keys work again
        assert app.query_one("#tabs", TabbedContent).active == "pane-queue"


async def test_typing_in_search_does_not_trigger_shortcuts():
    app, holder = make_app()
    async with app.run_test(size=(120, 30)) as pilot:
        await pilot.pause()
        await pilot.press("slash")
        await pilot.press(*"rqmtc1")                 # all of these are shortcuts when not typing
        await pilot.pause()
        assert app.query_one("#search", Input).value == "rqmtc1"
        assert holder["mux"].restarted == [] and not app._stopping and not app._stream


async def test_stream_mode_shows_everything_with_names():
    app, holder = make_app()
    async with app.run_test(size=(120, 30)) as pilot:
        await pilot.pause()
        await feed(app, holder, ("server", SERVER), ("queue", QUEUE), ("server", BROADCAST))
        await pilot.press("m")
        await pilot.pause()
        assert app.query_one("#stream").display and not app.query_one("#tabs").display
        rows = stream_texts(app)
        assert any(r.startswith("server") and "startup complete" in r for r in rows)
        assert any(r.startswith("queue") and "Queue worker started" in r for r in rows)
        assert any(r.startswith("logs") and "broadcasting" in r for r in rows)
        await pilot.press("m")
        assert app.query_one("#tabs").display


async def test_starts_in_stream_mode_when_asked():
    app, _ = make_app(stream=True)
    async with app.run_test(size=(120, 30)) as pilot:
        await pilot.pause()
        assert app.query_one("#stream").display and not app.query_one("#tabs").display


async def test_timestamps_toggle():
    app, holder = make_app()
    async with app.run_test(size=(120, 30)) as pilot:
        await pilot.pause()
        await feed(app, holder, ("server", SERVER))
        await pilot.pause()
        assert texts(app, "server")[0].startswith("INFO")
        await pilot.press("t")
        await pilot.pause()
        import re
        assert re.match(r"\d\d:\d\d:\d\d  INFO", texts(app, "server")[0])


async def test_restart_acts_on_the_active_tab():
    app, holder = make_app()
    async with app.run_test(size=(120, 30)) as pilot:
        await pilot.pause()
        await pilot.press("tab")                      # queue
        await pilot.press("r")
        await pilot.press("4")                        # logs belongs to the server process
        await pilot.press("r")
        await pilot.pause()
        assert holder["mux"].restarted == ["queue", "server"]


async def test_tab_label_follows_the_process_state():
    app, holder = make_app()
    async with app.run_test(size=(120, 30)) as pilot:
        await pilot.pause()
        holder["mux"].on_state("queue", "failed")
        await pilot.pause()
        label = app.query_one("#tabs", TabbedContent).get_tab("pane-queue").label
        assert label.plain == "● queue"
        assert any("red" in str(span.style) for span in label.spans)


async def test_clear_empties_the_active_tab_only():
    app, holder = make_app()
    async with app.run_test(size=(120, 30)) as pilot:
        await pilot.pause()
        await feed(app, holder, ("server", SERVER), ("queue", QUEUE))
        await pilot.press("c")
        await pilot.pause()
        assert texts(app, "server") == []
        assert len(app._lines["queue"]) == 1


async def test_quit_stops_the_multiplexer_and_exits():
    app, holder = make_app()
    async with app.run_test(size=(120, 30)) as pilot:
        await pilot.pause()
        await pilot.press("q")
        await pilot.pause()
    assert holder["mux"].cancelled
    assert app.return_value == 0


async def test_second_quit_press_kills_immediately():
    app, holder = make_app()
    async with app.run_test(size=(120, 30)) as pilot:
        await pilot.pause()
        app._stopping = True                          # a graceful stop is already under way
        await pilot.press("q")
        await pilot.pause()
    assert holder["mux"].killed


async def test_scrolling_up_is_not_undone_by_new_lines():
    app, holder = make_app()
    async with app.run_test(size=(120, 12)) as pilot:
        await pilot.pause()
        for i in range(80):
            holder["mux"].emit("server", f"INFO:     line {i}", "out")
        await pilot.pause()
        log = app.query_one("#log-server", RichLog)
        assert log.is_vertical_scroll_end                       # followed the output
        log.scroll_to(y=0, animate=False)
        await pilot.pause()
        holder["mux"].emit("server", "INFO:     late line", "out")
        await pilot.pause()
        assert log.scroll_y == 0                                # still where the reader left it
