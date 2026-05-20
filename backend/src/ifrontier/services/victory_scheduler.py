from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Dict, Optional
from ifrontier.core.logger import get_logger
from ifrontier.services.victory import VictoryService
from ifrontier.infra.sqlite.db import room_id_var
from ifrontier.services.news import NewsService

_log = get_logger(__name__)

class VictoryScheduler:
    def __init__(
        self,
        *,
        tick_interval_seconds: float = 5.0,
        broadcaster: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None,
        get_channel_size: Optional[Callable[[str], Awaitable[int]]] = None,
        room_settings: Optional[Dict[str, Any]] = None,
        news_service: Optional[NewsService] = None,
    ) -> None:
        self._tick_interval_seconds = float(tick_interval_seconds)
        self._broadcaster = broadcaster
        self._get_channel_size = get_channel_size
        
        self._stop = asyncio.Event()
        self._task: Optional[asyncio.Task[None]] = None
        self._victory_service = VictoryService()
        self._news_service = news_service
        
        # 默认设置，房间级配置会在这里覆盖，避免影响全局默认值
        self.settings = {
            "ultimate_owner_threshold": 1_500_000_000.0, # 15亿
            "mass_bankruptcy_mode": True,
            "min_active_players": 1,
            "time_limit_seconds": None, # 无限时
        }
        if room_settings:
            self.settings.update({k: v for k, v in room_settings.items() if v is not None})

    def start(self) -> None:
        if self._task is not None:
            return
        self._task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        self._stop.set()
        if self._task is None:
            return
        try:
            await self._task
        finally:
            self._task = None

    async def _run_loop(self) -> None:
        _log.info("VictoryScheduler started")
        while not self._stop.is_set():
            has_time_limit = bool(self.settings.get("time_limit_seconds"))
            # 检查是否有在线玩家，如果没有则跳过以节省 CPU
            if self._get_channel_size:
                try:
                    online = await self._get_channel_size("presence")
                except Exception:
                    online = 0
                if online <= 0 and not has_time_limit:
                    await asyncio.sleep(self._tick_interval_seconds)
                    continue

            try:
                # 1. 玩家个人结算更新 (在线程池中运行同步 DB 操作)
                if has_time_limit or (self._get_channel_size is None):
                    await self._process_player_settlements()
                elif self._get_channel_size:
                    try:
                        online = await self._get_channel_size("presence")
                    except Exception:
                        online = 0
                    if online > 0:
                        await self._process_player_settlements()
                
                # 2. 全局胜利条件检测
                result = await asyncio.to_thread(self._victory_service.check_global_victory, self.settings)
                if result and self._broadcaster:
                    _log.info(f"Global Victory Reached: {result}")
                    await self._broadcaster({
                        "event_type": "game.victory",
                        **result
                    })
                    await self._publish_victory_news(result)
                    # 这里可以选择停止游戏，但目前先只广播

            except Exception as e:
                _log.exception(f"VictoryScheduler tick error: {e}")

            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self._tick_interval_seconds)
            except asyncio.TimeoutError:
                pass

    async def _process_player_settlements(self) -> None:
        """更新所有玩家估值并检测破产。"""
        from ifrontier.infra.sqlite.db import get_connection
        conn = get_connection()
        
        # 获取所有人类玩家 ID
        player_ids = await asyncio.to_thread(self._get_all_player_ids, conn)
        
        for pid in player_ids:
            old_status = await asyncio.to_thread(self._get_player_status, conn, pid)
            # 拿到详细结算结果
            res = await asyncio.to_thread(self._victory_service.update_player_settlement, pid)
            new_status = res["status"]
            
            # 如果状态发生变化，广播事件
            if old_status != new_status and self._broadcaster:
                await self._broadcaster({
                    "event_type": "player.status_changed",
                    "player_id": pid,
                    "old_status": old_status,
                    "new_status": new_status,
                    "achievement": res["achievement"],
                    "message": res["message"],
                    "valuation": res["valuation"]
                })
                await self._publish_status_news(pid, old_status, new_status, res)

    async def _publish_status_news(self, player_id: str, old_status: str, new_status: str, result: Dict[str, Any]) -> None:
        if not self._news_service:
            return
        try:
            delivered, ev = self._news_service.broadcast_system_news(
                kind="MAJOR_EVENT",
                actor_id="system",
                channel="game",
                visibility_level="PUBLIC",
                truth_payload={
                    "event": "player.status_changed",
                    "player_id": player_id,
                    "old_status": old_status,
                    "new_status": new_status,
                    "achievement": result.get("achievement"),
                    "message": result.get("message"),
                    "valuation": result.get("valuation"),
                },
                symbols=[player_id],
            )
            if self._broadcaster:
                await self._broadcaster(ev.model_dump())
        except Exception as exc:
            _log.exception(f"Failed to publish status news for {player_id}: {exc}")

    async def _publish_victory_news(self, result: Dict[str, Any]) -> None:
        if not self._news_service:
            return
        try:
            delivered, ev = self._news_service.broadcast_system_news(
                kind="WORLD_EVENT",
                actor_id="system",
                channel="game",
                visibility_level="PUBLIC",
                truth_payload=result,
                symbols=[str(result.get("winner") or "NONE")],
            )
            if self._broadcaster:
                await self._broadcaster(ev.model_dump())
        except Exception as exc:
            _log.exception(f"Failed to publish victory news: {exc}")

    def _get_all_player_ids(self, conn) -> list[str]:
        rows = conn.execute("SELECT account_id FROM accounts WHERE owner_type = 'user'").fetchall()
        return [r["account_id"] for r in rows]

    def _get_player_status(self, conn, player_id: str) -> str:
        row = conn.execute("SELECT status FROM accounts WHERE account_id = ?", (player_id,)).fetchone()
        return str(row["status"]) if row else "ACTIVE"
