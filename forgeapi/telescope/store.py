from __future__ import annotations

import asyncio
import dataclasses
import uuid
from collections import deque
from datetime import date, datetime, timezone
from typing import Any


def _serializable(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _serializable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_serializable(i) for i in obj]
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    return obj

_MAX_ENTRIES = 200


@dataclasses.dataclass
class SqlRecord:
    sql: str
    duration_ms: float
    location: str
    params: Any = None


@dataclasses.dataclass
class LogRecord:
    level: str
    logger: str
    message: str
    time: str


@dataclasses.dataclass
class EventRecord:
    event: str
    listeners: list[str]
    background: bool


@dataclasses.dataclass
class JobRecord:
    job: str
    status: str          # queued | running | done | failed
    attempts: int
    duration_ms: float | None
    error: str | None


@dataclasses.dataclass
class RequestEntry:
    id: str
    method: str
    path: str
    query_string: str
    headers: dict[str, str]
    payload: Any
    timestamp: str
    status: int | None = None
    duration_ms: float | None = None
    response_body: Any = None
    queries: list[SqlRecord] = dataclasses.field(default_factory=list)
    logs: list[LogRecord] = dataclasses.field(default_factory=list)
    events: list[EventRecord] = dataclasses.field(default_factory=list)
    jobs: list[JobRecord] = dataclasses.field(default_factory=list)

    def summary(self) -> dict:
        return {
            "id": self.id,
            "method": self.method,
            "path": self.path,
            "status": self.status,
            "duration_ms": self.duration_ms,
            "timestamp": self.timestamp,
            "counts": {
                "queries": len(self.queries),
                "logs": len(self.logs),
                "events": len(self.events),
                "jobs": len(self.jobs),
            },
        }

    def to_dict(self) -> dict:
        return _serializable(dataclasses.asdict(self))


_MAX_WS_CONNECTIONS = 100


class ConnectionManager:
    """Manages active WebSocket connections and broadcasts events to all of them."""

    def __init__(self) -> None:
        self._connections: list[Any] = []

    async def connect(self, ws: Any) -> None:
        if len(self._connections) >= _MAX_WS_CONNECTIONS:
            await ws.close(code=1008)
            return
        await ws.accept()
        self._connections.append(ws)

    def disconnect(self, ws: Any) -> None:
        try:
            self._connections.remove(ws)
        except ValueError:
            pass

    async def broadcast(self, payload: dict) -> None:
        dead: list[Any] = []
        for ws in list(self._connections):
            try:
                await ws.send_json(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


manager = ConnectionManager()


class DebugStore:
    """In-memory circular store — keeps the last 200 request entries."""

    _store: deque[RequestEntry] = deque(maxlen=_MAX_ENTRIES)
    _index: dict[str, RequestEntry] = {}

    @classmethod
    def new_entry(
        cls,
        method: str,
        path: str,
        query_string: str = "",
        headers: dict | None = None,
        payload: Any = None,
    ) -> RequestEntry:
        return RequestEntry(
            id=str(uuid.uuid4()),
            method=method,
            path=path,
            query_string=query_string,
            headers=headers or {},
            payload=payload,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    @classmethod
    def push(cls, entry: RequestEntry) -> None:
        if len(cls._store) == cls._store.maxlen:
            oldest = cls._store[-1]
            cls._index.pop(oldest.id, None)
        cls._store.appendleft(entry)
        cls._index[entry.id] = entry
        try:
            asyncio.get_running_loop().create_task(
                manager.broadcast({"type": "entry", "data": entry.to_dict()})
            )
        except RuntimeError:
            pass

    @classmethod
    def all(cls) -> list[RequestEntry]:
        return list(cls._store)

    @classmethod
    def get(cls, entry_id: str) -> RequestEntry | None:
        return cls._index.get(entry_id)

    @classmethod
    def clear(cls) -> None:
        # Replace both structures atomically so a concurrent push() that already
        # grabbed a reference to the old deque/dict doesn't pollute the new state.
        cls._store = deque(maxlen=_MAX_ENTRIES)
        cls._index = {}
        try:
            asyncio.get_running_loop().create_task(
                manager.broadcast({"type": "clear"})
            )
        except RuntimeError:
            pass
