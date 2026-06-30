from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from .store import DebugStore, manager

router = APIRouter(prefix="/_forge/telescope", tags=["[forge:telescope]"])


@router.websocket("/ws")
async def telescope_ws(ws: WebSocket) -> None:
    await manager.connect(ws)
    await ws.send_json({"type": "init", "data": [e.to_dict() for e in DebugStore.all()]})
    try:
        while True:
            try:
                data = await ws.receive_json()
            except WebSocketDisconnect:
                raise
            except Exception:
                continue
            if isinstance(data, dict) and data.get("type") == "clear":
                DebugStore.clear()
    except WebSocketDisconnect:
        manager.disconnect(ws)
