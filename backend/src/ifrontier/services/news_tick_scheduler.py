from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Dict, Optional

from ifrontier.services.news_tick import NewsTickEngine


class NewsTickScheduler:
    def __init__(
        self,
        *,
        tick_engine: NewsTickEngine,
        tick_interval_seconds: float = 1.0,
        batch_size: int = 50,
        broadcaster: Callable[[Dict[str, Any]], Awaitable[None]],
    ) -> None:
        self._tick_engine = tick_engine
        self._tick_interval_seconds = float(tick_interval_seconds)
        self._batch_size = int(batch_size)
        self._broadcaster = broadcaster

        self._stop = asyncio.Event()
        self._task: Optional[asyncio.Task[None]] = None

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
                result = await self._tick_engine.tick(
                    now=None,
                    limit=self._batch_size,
                )
            except Exception:
                result = {"chains": []}

            # 广播 tick 产生的事件
            for chain in (result or {}).get("chains", []) or []:
                for action in (chain or {}).get("actions", []) or []:
                    for ev in (action or {}).get("events", []) or []:
                        if not ev:
                            continue
                        if isinstance(ev, dict):
                            await self._broadcaster(ev)

            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self._tick_interval_seconds)
            except asyncio.TimeoutError:
                pass
