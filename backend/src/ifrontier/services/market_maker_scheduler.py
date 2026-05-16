from __future__ import annotations

import asyncio
import os
from typing import Any, Awaitable, Callable, Dict, Optional

from ifrontier.core.logger import get_logger
from ifrontier.services.market_maker import MarketMaker, MarketMakerConfig

_log = get_logger(__name__)


class MarketMakerScheduler:
    def __init__(
        self,
        *,
        tick_interval_seconds: float = 2.0,
        broadcaster: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None,
        channel_for_online_stats: Optional[str] = None,
        get_channel_size: Optional[Callable[[str], Awaitable[int]]] = None,
    ) -> None:
        self._tick_interval_seconds = float(tick_interval_seconds)
        self._broadcaster = broadcaster

        self._channel_for_online_stats = str(channel_for_online_stats) if channel_for_online_stats else None
        self._get_channel_size = get_channel_size
        self._stop = asyncio.Event()
        self._task: Optional[asyncio.Task[None]] = None
        self._last_regen_day: Optional[int] = None  # 上次恢复的游戏日编号
        self._last_health_broadcast: Optional[str] = None  # 上次广播的健康等级

        cfg = MarketMakerConfig(
            account_id=str(os.getenv("IF_MARKET_MAKER_ACCOUNT_ID") or "mm:1"),
            spread_pct=float(os.getenv("IF_MARKET_MAKER_SPREAD_PCT") or "0.02"),
            min_qty=float(os.getenv("IF_MARKET_MAKER_MIN_QTY") or "10.0"),
        )
        self._mm = MarketMaker(cfg=cfg)

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
        from ifrontier.services.game_time import load_game_time_config_from_env
        from ifrontier.services.market_session import get_market_session, MarketPhase

        while not self._stop.is_set():
            if self._get_channel_size and self._channel_for_online_stats:
                try:
                    online = int(await self._get_channel_size(self._channel_for_online_stats))
                except Exception:
                    online = 0
                if online <= 0:
                    try:
                        await asyncio.wait_for(self._stop.wait(), timeout=self._tick_interval_seconds)
                    except asyncio.TimeoutError:
                        pass
                    continue
            try:
                gt_cfg = load_game_time_config_from_env()
                session = get_market_session(cfg=gt_cfg)

                # ── 每日恢复：检测新游戏日，在开盘时触发一次 daily_regen ──
                game_day = self._get_game_day(gt_cfg)
                if game_day is not None and game_day != self._last_regen_day:
                    self._last_regen_day = game_day
                    try:
                        await asyncio.to_thread(self._mm.daily_regen)
                        _log.info("MarketMaker daily regen applied for game day %s", game_day)
                    except Exception as regen_exc:
                        _log.exception("MarketMaker daily regen failed: %s", regen_exc)

                if session.phase == MarketPhase.TRADING:
                    from ifrontier.infra.sqlite.news_chain import count_chains_by_status
                    active_chains_count = await asyncio.to_thread(count_chains_by_status, "INCUBATING")

                    matches = await asyncio.to_thread(self._mm.tick_once, active_chains_count=active_chains_count)

                    # 广播成交事件
                    if self._broadcaster and matches:
                        for m in matches:
                            await self._broadcaster(m.executed_event.model_dump())

                    # ── 健康度事件广播 ──
                    await self._broadcast_health_events()

            except Exception as exc:
                _log.exception("MarketMaker tick error: %s", exc)

            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self._tick_interval_seconds)
            except asyncio.TimeoutError:
                pass

    @staticmethod
    def _get_game_day(cfg: Any) -> Optional[int]:
        """从游戏时间配置推算当前游戏日编号。"""
        try:
            from ifrontier.services.game_time import game_time_now
            snap = game_time_now(cfg=cfg)
            return snap.game_day_index
        except Exception:
            return None

    async def _broadcast_health_events(self) -> None:
        """根据做市商健康度变化广播市场事件。"""
        from ifrontier.services.market_maker import (
            HEALTH_WARN_THRESHOLD,
            HEALTH_CRITICAL_THRESHOLD,
            HEALTH_DEAD_THRESHOLD,
        )

        health = self._mm.last_health

        if health < HEALTH_DEAD_THRESHOLD:
            level = "BANKRUPT"
        elif health < HEALTH_CRITICAL_THRESHOLD:
            level = "CRITICAL"
        elif health < HEALTH_WARN_THRESHOLD:
            level = "WARNING"
        else:
            level = "NORMAL"

        # 只在等级变化时广播一次
        if level == self._last_health_broadcast:
            return
        self._last_health_broadcast = level

        if level == "NORMAL":
            return  # 恢复正常不广播

        event_payload = {
            "event_type": "market.maker_health",
            "level": level,
            "health": round(health, 4),
            "message": {
                "WARNING": "做市商流动性开始下降，交易点差扩大。市场波动加剧。",
                "CRITICAL": "做市商濒临破产！流动性严重不足，极端点差，市场即将进入自由交易模式。",
                "BANKRUPT": "做市商已破产！市场进入无做市商模式，所有交易完全由玩家撮合。",
            }.get(level, ""),
        }

        _log.warning("MarketMaker health event: %s (health=%.2f%%)", level, health * 100)

        if self._broadcaster:
            try:
                await self._broadcaster(event_payload)
            except Exception:
                pass
