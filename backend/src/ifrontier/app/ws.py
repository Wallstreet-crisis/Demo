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

    async def get_channel_size(self, channel: str) -> int:
        async with self._lock:
            return int(len(self._channels.get(channel, set())))

    async def get_stats(self) -> Dict[str, int]:
        async with self._lock:
            all_sockets: Set[WebSocket] = set()
            for ch_socks in self._channels.values():
                all_sockets |= set(ch_socks)

            stats: Dict[str, int] = {"total_connections": int(len(all_sockets))}
            for ch, ch_socks in self._channels.items():
                stats[f"channel:{ch}"] = int(len(ch_socks))
            return stats


hub = WsHub()


@router.websocket("/ws/{channel}")
async def ws_channel(ws: WebSocket, channel: str) -> None:
    await hub.join(channel, ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        await hub.leave(channel, ws)
