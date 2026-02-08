from __future__ import annotations

import asyncio
import os
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
        channel_for_online_stats: Optional[str] = None,
        get_channel_size: Optional[Callable[[str], Awaitable[int]]] = None,
    ) -> None:
        self._tick_engine = tick_engine
        self._tick_interval_seconds = float(tick_interval_seconds)
        self._batch_size = int(batch_size)
        self._broadcaster = broadcaster

        self._channel_for_online_stats = str(channel_for_online_stats) if channel_for_online_stats else None
        self._get_channel_size = get_channel_size

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
        verbose = str(os.getenv("IF_SCHEDULER_VERBOSE") or "").strip().lower() in {"1", "true", "yes", "on"}
        if verbose:
            print(f"[NewsTickScheduler] Starting loop (interval={self._tick_interval_seconds}s)")
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
                result = await self._tick_engine.tick(
                    now=None,
                    limit=self._batch_size,
                )
                if (result or {}).get("chains"):
                    if verbose:
                        print(f"[NewsTickScheduler] Ticked {len(result['chains'])} active chains")
            except Exception as e:
                if verbose:
                    print(f"[NewsTickScheduler] Error: {e}")
                result = {"chains": []}

            # 广播 tick 产生的系统生成事件 (Spawned events)
            for ev in (result or {}).get("spawned_events", []) or []:
                if ev and isinstance(ev, dict):
                    await self._broadcaster(ev)

            # 广播 tick 产生的事件 (Chains)
            for chain in (result or {}).get("chains", []) or []:
                for action in (chain or {}).get("actions", []) or []:
                    # 1) 普通事件 (News events)
                    for ev in (action or {}).get("events", []) or []:
                        if ev and isinstance(ev, dict):
                            await self._broadcaster(ev)

                    # 2) 紧急 Bot 反应事件 (Emergency bot reactions)
                    for ev in (action or {}).get("emergency_events", []) or []:
                        if ev and isinstance(ev, dict):
                            await self._broadcaster(ev)

            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self._tick_interval_seconds)
            except asyncio.TimeoutError:
                pass
