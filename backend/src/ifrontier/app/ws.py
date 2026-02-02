from __future__ import annotations

import asyncio
from typing import Dict, Set

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()


class WsHub:
    def __init__(self) -> None:
        self._channels: Dict[str, Set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def join(self, channel: str, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._channels.setdefault(channel, set()).add(ws)

    async def leave(self, channel: str, ws: WebSocket) -> None:
        async with self._lock:
            if channel in self._channels:
                self._channels[channel].discard(ws)
                if not self._channels[channel]:
                    del self._channels[channel]

    async def broadcast_json(self, channel: str, payload: dict) -> None:
        async with self._lock:
            targets = list(self._channels.get(channel, set()))
        for ws in targets:
            try:
                await ws.send_json(payload)
            except Exception:
                await self.leave(channel, ws)


hub = WsHub()


@router.websocket("/ws/{channel}")
async def ws_channel(ws: WebSocket, channel: str) -> None:
    await hub.join(channel, ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        await hub.leave(channel, ws)
