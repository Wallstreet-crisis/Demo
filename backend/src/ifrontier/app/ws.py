from __future__ import annotations

import asyncio
import json
import re
from typing import Dict, List, Set

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from ifrontier.infra.sqlite.db import room_id_var
from ifrontier.app.room_meta import room_exists
from ifrontier.core.logger import get_logger

router = APIRouter()
_log = get_logger(__name__)

_CHANNEL_RE = re.compile(r"^[a-zA-Z0-9_\.\-]{1,64}$")
_ROOM_ID_RE = re.compile(r"^[a-zA-Z0-9_\-]{1,64}$")

# 单次并行发送超时（秒），防止慢客户端拖住整个广播
_SEND_TIMEOUT = 2.0


class WsHub:
    """高性能 WebSocket 广播中枢。

    关键优化：
    1. **预序列化**：payload 只 JSON.dumps 一次，所有客户端复用同一份 bytes。
    2. **并行发送**：asyncio.gather 并发推送，不再逐个 await。
    3. **发送超时**：单个慢客户端不会阻塞其他人。
    4. **批量广播**：broadcast_many 一次性推送到多个 channel，减少锁竞争。
    5. **定期清理**：后台任务每 30s 清理断开的死连接。
    """

    def __init__(self) -> None:
        self._channels: Dict[str, Set[WebSocket]] = {}
        self._lock = asyncio.Lock()
        self._sweep_task: asyncio.Task | None = None

    def start_sweep(self) -> None:
        if self._sweep_task is None or self._sweep_task.done():
            self._sweep_task = asyncio.ensure_future(self._sweep_loop())

    async def _sweep_loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(30)
                await self._sweep_dead()
            except Exception as exc:
                _log.warning("Sweep loop error: %s", exc)
                # 短暂休息后继续
                await asyncio.sleep(5)

    async def _sweep_dead(self) -> None:
        async with self._lock:
            for key in list(self._channels.keys()):
                alive = set()
                for ws in self._channels[key]:
                    try:
                        if ws.client_state == WebSocketState.CONNECTED:
                            alive.add(ws)
                    except Exception:
                        pass
                if alive:
                    self._channels[key] = alive
                else:
                    del self._channels[key]

    async def join(self, room_id: str, channel: str, ws: WebSocket) -> None:
        await ws.accept()
        key = f"room:{room_id}:{channel}"
        async with self._lock:
            self._channels.setdefault(key, set()).add(ws)
        self.start_sweep()

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

        # 预序列化：只编码一次
        data = json.dumps(payload, ensure_ascii=False, default=str)

        async with self._lock:
            targets = list(self._channels.get(key, set()))

        if not targets:
            return

        dead: List[WebSocket] = []
        dead_lock = asyncio.Lock()

        async def _send(ws: WebSocket) -> None:
            try:
                await asyncio.wait_for(ws.send_text(data), timeout=_SEND_TIMEOUT)
            except Exception:
                async with dead_lock:
                    dead.append(ws)

        await asyncio.gather(*(_send(ws) for ws in targets))

        if dead:
            async with self._lock:
                bucket = self._channels.get(key)
                if bucket:
                    for ws in dead:
                        bucket.discard(ws)
                    if not bucket:
                        del self._channels[key]

    async def broadcast_many(self, channels: List[str], payload: dict, room_id: str | None = None) -> None:
        """一次性向多个 channel 广播同一条消息，共享预序列化结果，减少锁次数。"""
        if room_id is None:
            room_id = room_id_var.get()

        data = json.dumps(payload, ensure_ascii=False, default=str)

        # 收集所有目标（去重同一 ws 出现在多个 channel 的情况）
        all_targets: Set[WebSocket] = set()
        keys: List[str] = []
        async with self._lock:
            for ch in channels:
                key = f"room:{room_id}:{ch}"
                keys.append(key)
                bucket = self._channels.get(key)
                if bucket:
                    all_targets |= bucket

        if not all_targets:
            return

        dead: List[WebSocket] = []
        dead_lock = asyncio.Lock()

        async def _send(ws: WebSocket) -> None:
            try:
                await asyncio.wait_for(ws.send_text(data), timeout=_SEND_TIMEOUT)
            except Exception:
                async with dead_lock:
                    dead.append(ws)

        await asyncio.gather(*(_send(ws) for ws in all_targets))

        if dead:
            dead_set = set(dead)
            async with self._lock:
                for key in keys:
                    bucket = self._channels.get(key)
                    if bucket:
                        bucket -= dead_set
                        if not bucket:
                            del self._channels[key]

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
            try:
                await asyncio.wait_for(ws.receive_text(), timeout=60.0)
            except asyncio.TimeoutError:
                # 60 秒无消息，发送 ping 检测连接
                try:
                    await ws.send_text('{"type":"ping"}')
                except Exception:
                    break
            except Exception:
                break
    except WebSocketDisconnect:
        pass
    finally:
        await hub.leave(room_id, channel, ws)


@router.websocket("/ws/{channel}")
async def ws_channel_default(ws: WebSocket, channel: str) -> None:
    if not _CHANNEL_RE.match(channel):
        await ws.close(code=4400, reason="Invalid channel format")
        return
    await hub.join("default", channel, ws)
    try:
        while True:
            try:
                await asyncio.wait_for(ws.receive_text(), timeout=60.0)
            except asyncio.TimeoutError:
                try:
                    await ws.send_text('{"type":"ping"}')
                except Exception:
                    break
            except Exception:
                break
    except WebSocketDisconnect:
        pass
    finally:
        await hub.leave("default", channel, ws)
