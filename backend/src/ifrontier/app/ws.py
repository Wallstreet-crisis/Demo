from __future__ import annotations

import asyncio
import re
from typing import Dict, Set

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ifrontier.infra.sqlite.db import room_id_var
from ifrontier.app.room_meta import room_exists

router = APIRouter()

# 允许的 channel 名称白名单（正则）
_CHANNEL_RE = re.compile(r"^[a-zA-Z0-9_\-]{1,64}$")
# 允许的 room_id 格式
_ROOM_ID_RE = re.compile(r"^[a-zA-Z0-9_\-]{1,64}$")


class WsHub:
    def __init__(self) -> None:
        self._channels: Dict[str, Set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def join(self, room_id: str, channel: str, ws: WebSocket) -> None:
        await ws.accept()
        key = f"room:{room_id}:{channel}"
        async with self._lock:
            self._channels.setdefault(key, set()).add(ws)

    async def leave(self, room_id: str, channel: str, ws: WebSocket) -> None:
        key = f"room:{room_id}:{channel}"
        async with self._lock:
            if key in self._channels:
                self._channels[key].discard(ws)
                if not self._channels[key]:
                    del self._channels[key]

    async def broadcast_json(self, channel: str, payload: dict, room_id: str | None = None) -> None:
        if room_id is None:
            room_id = room_id_var.get()
        key = f"room:{room_id}:{channel}"
        async with self._lock:
            targets = list(self._channels.get(key, set()))
        for ws in targets:
            try:
                await ws.send_json(payload)
            except Exception:
                await self.leave(room_id, channel, ws)

    async def get_channel_size(self, channel: str, room_id: str | None = None) -> int:
        if room_id is None:
            room_id = room_id_var.get()
        key = f"room:{room_id}:{channel}"
        async with self._lock:
            return int(len(self._channels.get(key, set())))

    async def get_stats(self) -> Dict[str, int]:
        async with self._lock:
            all_sockets: Set[WebSocket] = set()
            for ch_socks in self._channels.values():
                all_sockets |= set(ch_socks)

            stats: Dict[str, int] = {"total_connections": int(len(all_sockets))}
            for ch, ch_socks in self._channels.items():
                stats[ch] = int(len(ch_socks))
            return stats


hub = WsHub()


@router.websocket("/ws/{room_id}/{channel}")
async def ws_channel_room(ws: WebSocket, room_id: str, channel: str) -> None:
    if not _ROOM_ID_RE.match(room_id) or not _CHANNEL_RE.match(channel):
        await ws.close(code=4400, reason="Invalid room_id or channel format")
        return
    if room_id != "default" and not room_exists(room_id):
        await ws.close(code=4404, reason="Room not found")
        return
    await hub.join(room_id, channel, ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        await hub.leave(room_id, channel, ws)


@router.websocket("/ws/{channel}")
async def ws_channel_default(ws: WebSocket, channel: str) -> None:
    if not _CHANNEL_RE.match(channel):
        await ws.close(code=4400, reason="Invalid channel format")
        return
    await hub.join("default", channel, ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        await hub.leave("default", channel, ws)
