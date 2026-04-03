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
                # 检查市场是否开市
                gt_cfg = load_game_time_config_from_env()
                session = get_market_session(cfg=gt_cfg)

                if session.phase == MarketPhase.TRADING:
                    # 使用 SQLite 统计 INCUBATING 状态的新闻链数量（在线程池中执行）
                    from ifrontier.infra.sqlite.news_chain import count_chains_by_status
                    active_chains_count = await asyncio.to_thread(count_chains_by_status, "INCUBATING")

                    # 在线程池中运行同步的 tick_once
                    matches = await asyncio.to_thread(self._mm.tick_once, active_chains_count=active_chains_count)

                    # 广播成交事件
                    if self._broadcaster and matches:
                        for m in matches:
                            await self._broadcaster(m.executed_event.model_dump())
            except Exception as exc:
                _log.exception("MarketMaker tick error: %s", exc)

            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self._tick_interval_seconds)
            except asyncio.TimeoutError:
                pass
