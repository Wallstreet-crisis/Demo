from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Dict, Optional

from ifrontier.services.commonbot_emergency import CommonBotEmergencyRunner
from ifrontier.services.game_time import load_game_time_config_from_env
from ifrontier.services.market_session import MarketPhase, get_market_session


class MarketSessionScheduler:
    def __init__(
        self,
        *,
        runner: CommonBotEmergencyRunner,
        tick_interval_seconds: float = 1.0,
        broadcaster: Callable[[Dict[str, Any]], Awaitable[None]],
    ) -> None:
        self._runner = runner
        self._tick_interval_seconds = float(tick_interval_seconds)
        self._broadcaster = broadcaster

        self._stop = asyncio.Event()
        self._task: Optional[asyncio.Task[None]] = None
        self._last_phase: Optional[str] = None

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
        while not self._stop.is_set():
            try:
                cfg = load_game_time_config_from_env()
                snap = get_market_session(cfg=cfg)
                cur_phase = snap.phase.value

                if self._last_phase is not None:
                    if self._last_phase != MarketPhase.TRADING.value and cur_phase == MarketPhase.TRADING.value:
                        events = await self._runner.maybe_react_on_market_open()
                        for ev in events:
                            await self._broadcaster(ev.model_dump())

                self._last_phase = cur_phase
            except Exception:
                # 必须异常隔离：任何一次检测失败不影响调度循环
                pass

            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self._tick_interval_seconds)
            except asyncio.TimeoutError:
                pass
