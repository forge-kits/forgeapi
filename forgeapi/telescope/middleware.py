from __future__ import annotations

import json
import logging
import time

from starlette.datastructures import Headers
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .context import clear_current, set_current
from .store import DebugStore

logger = logging.getLogger("forgeapi.telescope")

_SKIP_PREFIXES = ("/_forge/telescope", "/docs", "/redoc", "/openapi.json")
_SENSITIVE_HEADERS = frozenset({"authorization", "cookie", "x-api-key", "x-telegram-init-data"})


def _filter_headers(headers: dict[str, str]) -> dict[str, str]:
    return {k: ("***" if k.lower() in _SENSITIVE_HEADERS else v) for k, v in headers.items()}


def _parse_payload(body: bytes, content_type: str) -> object:
    if not body:
        return None
    if "application/json" in content_type:
        try:
            return json.loads(body)
        except Exception:
            pass
    return body.decode("utf-8", errors="replace")[:2000]


class DebugMiddleware:
    """Pure ASGI middleware — runs everything in one task so ContextVar works."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path: str = scope.get("path", "")
        if any(path.startswith(p) for p in _SKIP_PREFIXES):
            await self.app(scope, receive, send)
            return

        # --- read request body, then replay for inner app ---
        body_bytes = b""
        more_body = True
        while more_body:
            msg = await receive()
            if msg["type"] == "http.request":
                body_bytes += msg.get("body", b"")
                more_body = msg.get("more_body", False)
            else:
                more_body = False

        replayed = False

        async def replay_receive() -> Message:
            nonlocal replayed
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": body_bytes, "more_body": False}
            return await receive()

        # --- create entry ---
        req_headers = dict(Headers(scope=scope))
        content_type = req_headers.get("content-type", "")
        entry = DebugStore.new_entry(
            method=scope.get("method", "GET"),
            path=path,
            query_string=scope.get("query_string", b"").decode("utf-8", errors="replace"),
            headers=_filter_headers(req_headers),
            payload=_parse_payload(body_bytes, content_type),
        )
        set_current(entry)

        # --- intercept response ---
        resp_status: int | None = None
        resp_content_type = ""
        resp_chunks: list[bytes] = []

        async def capture_send(message: Message) -> None:
            nonlocal resp_status, resp_content_type
            if message["type"] == "http.response.start":
                resp_status = message.get("status")
                resp_headers = Headers(raw=message.get("headers", []))
                resp_content_type = resp_headers.get("content-type", "")
            elif message["type"] == "http.response.body":
                resp_chunks.append(message.get("body", b""))
            await send(message)

        start = time.perf_counter()
        try:
            # Single await — no new task spawned, ContextVar is visible everywhere inside
            await self.app(scope, replay_receive, capture_send)
        finally:
            entry.duration_ms = round((time.perf_counter() - start) * 1000, 3)
            entry.status = resp_status
            entry.response_body = _parse_payload(b"".join(resp_chunks), resp_content_type)
            DebugStore.push(entry)
            clear_current()
