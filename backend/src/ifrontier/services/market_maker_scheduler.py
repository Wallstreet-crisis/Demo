from __future__ import annotations

import asyncio
import os
from typing import Any, Awaitable, Callable, Dict, Optional

from ifrontier.services.market_maker import MarketMaker, MarketMakerConfig


class MarketMakerScheduler:
    def __init__(
        self,
        *,
        driver: Any = None,
        tick_interval_seconds: float = 2.0,
        broadcaster: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None,
    ) -> None:
        self._driver = driver
        self._tick_interval_seconds = float(tick_interval_seconds)
        self._broadcaster = broadcaster
        self._stop = asyncio.Event()
        self._task: Optional[asyncio.Task[None]] = None
        
        cfg = MarketMakerConfig(
            account_id=str(os.getenv("IF_MARKET_MAKER_ACCOUNT_ID") or "bot:inst:1"),
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
            try:
                # 检查市场是否开市
                gt_cfg = load_game_time_config_from_env()
                session = get_market_session(cfg=gt_cfg)
                
                if session.phase == MarketPhase.TRADING:
                    active_chains_count = 0
                    if self._driver:
                        with self._driver.session() as neo_session:
                            res = neo_session.run("MATCH (ch:NewsChain {phase: 'INCUBATING'}) RETURN count(ch) as c").single()
                            active_chains_count = int(res["c"]) if res else 0

                    # 在线程池中运行同步的 tick_once
                    matches = await asyncio.to_thread(self._mm.tick_once, active_chains_count=active_chains_count)
                    
                    # 广播成交事件
                    if self._broadcaster and matches:
                        for m in matches:
                            await self._broadcaster(m.executed_event.model_dump())
            except Exception as exc:
                import traceback
                traceback.print_exc()
                print(f"[MarketMakerScheduler] Error: {exc}")
                pass

            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self._tick_interval_seconds)
            except asyncio.TimeoutError:
                pass
