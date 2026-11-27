"""Run several commands side by side, stream their output, and keep them alive.

Used by the dev ``forgeapi runserver``: the server, the queue worker and the scheduler in one terminal.
The multiplexer knows nothing about how output is shown: it calls ``emit`` for every line and ``on_state``
when a process changes state, so the same code drives the plain stream and the tabbed interface.
"""
from __future__ import annotations

import asyncio
import os
import re
import signal
import time
from dataclasses import dataclass, field
from typing import Callable

#: ``emit(name, line, kind)``: ``kind`` is ``"out"`` for process output, ``"status"`` for our own notices.
Emit = Callable[[str, str, str], None]
#: ``on_state(name, state)`` with one of the ``STATE_*`` values.
OnState = Callable[[str, str], None]

STATE_STARTING = "starting"
STATE_RUNNING = "running"
STATE_RESTARTING = "restarting"
STATE_EXITED = "exited"
STATE_FAILED = "failed"      # crashed too often, will not be restarted until asked
STATE_STOPPED = "stopped"

_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


@dataclass
class Proc:
    name: str
    argv: list[str]
    #: Stopping this one stops everything (the server).  Others may exit on their own.
    critical: bool = False
    env: dict[str, str] = field(default_factory=dict)
    #: Text of the output line that means "up and running".  The next process starts only after it
    #: (or after ``ready_timeout``), so processes do not race for the same SQLite file at startup.
    ready: str | None = None


class Multiplexer:
    """Starts every :class:`Proc`, reports its output and state, and stops them all together.

    * A process that exits on its own is restarted (non-critical ones, when ``auto_restart`` is on) after a
      growing pause.  After ``max_crashes`` exits within ``crash_window`` seconds it is given up
      (``STATE_FAILED``) until :meth:`restart` is called.
    * The critical process (the server) ending ends the run: everything else is stopped.
    * Stop order for each process: SIGINT (what Ctrl+C would send, so uvicorn and the workers shut down
      gracefully), then SIGTERM after ``grace`` seconds, then SIGKILL after ``grace`` more.
    """

    def __init__(
        self,
        procs: list[Proc],
        emit: Emit,
        *,
        on_state: OnState | None = None,
        auto_restart: bool = True,
        grace: float = 5.0,
        ready_timeout: float = 20.0,
        max_crashes: int = 5,
        crash_window: float = 60.0,
        backoff: float = 1.0,
    ) -> None:
        self._procs = {p.name: p for p in procs}
        self._order = [p.name for p in procs]
        self._emit = emit
        self._on_state = on_state or (lambda name, state: None)
        self._auto_restart = auto_restart
        self._grace = grace
        self._ready_timeout = ready_timeout
        self._max_crashes = max_crashes
        self._crash_window = crash_window
        self._backoff = backoff

        self._running: dict[str, asyncio.subprocess.Process] = {}
        self._readers: dict[str, asyncio.Task] = {}
        self._ready: dict[str, asyncio.Event] = {}
        self._wanted_restart: set[str] = set()
        self._crashes: dict[str, list[float]] = {}
        self._stopping = False
        self._states: dict[str, str] = {}
        self._supervisors: dict[str, asyncio.Task] = {}

    @property
    def names(self) -> list[str]:
        return list(self._order)

    def state(self, name: str) -> str:
        return self._states.get(name, STATE_STARTING)

    # ── run ──────────────────────────────────────────────────────────────────

    async def run(self) -> int:
        """Run until the critical process exits (or this task is cancelled).  Returns its exit code."""
        try:
            for name in self._order:
                proc = self._procs[name]
                await self._spawn(proc)
                await self._wait_ready(proc)
                self._supervisors[name] = asyncio.create_task(self._supervise(proc), name=f"supervise:{name}")

            critical = [self._supervisors[n] for n in self._order if self._procs[n].critical]
            if not critical:
                await asyncio.gather(*self._supervisors.values())
                return 0
            done, _ = await asyncio.wait(critical, return_when=asyncio.FIRST_COMPLETED)
            return next(iter(done)).result()
        finally:
            await self._stop_all()

    async def restart(self, name: str) -> None:
        """Stop *name* and start it again.  Also revives a process that was given up."""
        proc = self._procs.get(name)
        if proc is None:
            return
        self._crashes.pop(name, None)
        child = self._running.get(name)
        if child is not None and child.returncode is None:
            self._wanted_restart.add(name)
            self._set_state(name, STATE_RESTARTING)
            self._emit(name, "restarting", "status")
            await self._stop(name, child, quiet=True)
            return
        # nothing running: either given up, or waiting out a backoff pause
        supervisor = self._supervisors.get(name)
        if supervisor is not None and not supervisor.done():
            supervisor.cancel()
        self._emit(name, "restarting", "status")
        await self._spawn(proc)
        self._supervisors[name] = asyncio.create_task(self._supervise(proc), name=f"supervise:{name}")

    # ── supervision ──────────────────────────────────────────────────────────

    async def _supervise(self, proc: Proc) -> int:
        """Keep one process alive.  Returns its exit code when it ends for good."""
        name = proc.name
        while True:
            child = self._running[name]
            code = await child.wait()
            await self._drain(name)
            self._running.pop(name, None)

            if self._stopping:
                return code
            if name in self._wanted_restart:
                self._wanted_restart.discard(name)
                await self._spawn(proc)
                continue

            self._emit(name, f"exited with code {code}", "status")
            if proc.critical:
                self._set_state(name, STATE_EXITED)
                return code
            if not self._auto_restart:
                self._set_state(name, STATE_EXITED)
                return code

            now = time.monotonic()
            recent = [t for t in self._crashes.get(name, []) if now - t < self._crash_window] + [now]
            self._crashes[name] = recent
            if len(recent) >= self._max_crashes:
                self._set_state(name, STATE_FAILED)
                self._emit(name, f"crashed {len(recent)} times in {self._crash_window:g}s, not restarting (press r)", "status")
                return code
            pause = min(self._backoff * 2 ** (len(recent) - 1), 10.0)
            self._set_state(name, STATE_RESTARTING)
            self._emit(name, f"restarting in {pause:g}s", "status")
            await asyncio.sleep(pause)
            if self._stopping:
                return code
            await self._spawn(proc)

    # ── processes ────────────────────────────────────────────────────────────

    async def _spawn(self, proc: Proc) -> None:
        env = {**os.environ, "PYTHONUNBUFFERED": "1", "FORCE_COLOR": "1", **proc.env}
        kwargs: dict = {}
        if os.name != "nt":
            kwargs["start_new_session"] = True      # Ctrl+C in the terminal reaches only us
        self._set_state(proc.name, STATE_STARTING)
        child = await asyncio.create_subprocess_exec(
            *proc.argv,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env=env,
            limit=2**20,
            **kwargs,
        )
        self._running[proc.name] = child
        self._ready[proc.name] = asyncio.Event()
        self._readers[proc.name] = asyncio.create_task(self._read(proc, child), name=f"read:{proc.name}")
        if not proc.ready:
            self._set_state(proc.name, STATE_RUNNING)

    async def _wait_ready(self, proc: Proc) -> None:
        if not proc.ready:
            return
        child = self._running[proc.name]
        up = asyncio.create_task(self._ready[proc.name].wait())
        gone = asyncio.create_task(child.wait())
        done, pending = await asyncio.wait({up, gone}, timeout=self._ready_timeout, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
        if not done:
            self._emit(proc.name, f"not ready after {self._ready_timeout:g}s, starting the rest anyway", "status")
            self._set_state(proc.name, STATE_RUNNING)

    async def _read(self, proc: Proc, child: asyncio.subprocess.Process) -> None:
        assert child.stdout is not None
        while True:
            raw = await child.stdout.readline()
            if not raw:
                return
            line = raw.decode(errors="replace").rstrip("\r\n")
            self._emit(proc.name, line, "out")
            if proc.ready and not self._ready[proc.name].is_set() and proc.ready in _ANSI.sub("", line):
                self._ready[proc.name].set()
                self._set_state(proc.name, STATE_RUNNING)

    async def _drain(self, name: str) -> None:
        """Let the reader print what the process wrote just before it exited."""
        reader = self._readers.get(name)
        if reader is not None:
            try:
                await asyncio.wait_for(asyncio.shield(reader), 1.0)
            except asyncio.TimeoutError:
                pass

    def _set_state(self, name: str, state: str) -> None:
        if self._states.get(name) != state:
            self._states[name] = state
            self._on_state(name, state)

    # ── stopping ─────────────────────────────────────────────────────────────

    async def _stop_all(self) -> None:
        self._stopping = True
        for task in self._supervisors.values():
            if not task.done() and task is not asyncio.current_task():
                task.cancel()
        for name, child in list(self._running.items()):
            await self._stop(name, child)
            self._set_state(name, STATE_STOPPED)
        self._running.clear()
        if self._readers:
            await asyncio.wait(list(self._readers.values()), timeout=self._grace)
            for task in self._readers.values():
                task.cancel()

    async def _stop(self, name: str, child: asyncio.subprocess.Process, *, quiet: bool = False) -> None:
        if child.returncode is not None:
            return
        for sig, wait in ((signal.SIGINT, self._grace), (signal.SIGTERM, self._grace), (signal.SIGKILL, None)):
            self._signal(child, sig)
            try:
                await asyncio.wait_for(child.wait(), wait)
                if not quiet:
                    self._emit(name, "stopped", "status")
                return
            except asyncio.TimeoutError:
                continue

    def kill_now(self) -> None:
        """Last resort for the caller's ``finally``: SIGKILL whatever still runs (a second Ctrl+C during shutdown)."""
        for child in self._running.values():
            if child.returncode is None:
                self._signal(child, signal.SIGKILL)

    @staticmethod
    def _signal(child: asyncio.subprocess.Process, sig: int) -> None:
        try:
            if os.name == "nt":
                child.terminate() if sig != signal.SIGKILL else child.kill()
            else:
                os.killpg(child.pid, sig)
        except (ProcessLookupError, PermissionError):
            pass
