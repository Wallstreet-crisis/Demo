from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Dict, List, Optional

from ifrontier.infra.sqlite.hosting import list_enabled_hosting_users, upsert_hosting_state
from ifrontier.services.user_capabilities import UserCapabilityFacade
from ifrontier.services.user_hosting_agent import UserHostingAgent


class HostingScheduler:
    def __init__(
        self,
        *,
        min_players: int = 8,
        tick_interval_seconds: float = 1.0,
        max_per_tick: int = 2,
        channel_for_online_stats: str = "events",
        get_channel_size: Callable[[str], Awaitable[int]],
        broadcaster: Callable[[Dict[str, Any]], Awaitable[None]],
        make_facade: Callable[[str], UserCapabilityFacade],
    ) -> None:
        self._min_players = int(min_players)
        self._tick_interval_seconds = float(tick_interval_seconds)
        self._max_per_tick = int(max_per_tick)
        self._channel_for_online_stats = str(channel_for_online_stats)
        self._get_channel_size = get_channel_size
        self._broadcaster = broadcaster
        self._make_facade = make_facade

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
                await self.tick_once()
            except Exception:
                # 必须异常隔离：任何一次 tick 失败不影响调度循环
                pass

            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self._tick_interval_seconds)
            except asyncio.TimeoutError:
                pass

    async def tick_once(self) -> None:
        humans = int(await self._get_channel_size(self._channel_for_online_stats))
        missing = max(0, self._min_players - humans)
        
        print(f"[HostingScheduler] Tick: humans={humans}, min_required={self._min_players}, missing={missing}")

        if missing <= 0:
            # 在线人数充足：把托管用户状态刷新为 IDLE
            return

        quota = min(int(missing), int(self._max_per_tick))
        enabled = list_enabled_hosting_users(limit=200)

        bot_candidates = [st for st in enabled if str(st.user_id).startswith("bot:")]
        human_candidates = [st for st in enabled if not str(st.user_id).startswith("bot:")]

        print(
            f"[HostingScheduler] Available enabled bots: {len(bot_candidates)}; enabled non-bot: {len(human_candidates)}"
        )

        picked = bot_candidates[:quota]
        if not picked:
            print("[HostingScheduler] No enabled bots found to pick.")
            return

        for st in picked:
            print(f"[HostingScheduler] Activating bot: {st.user_id}")
            upsert_hosting_state(user_id=st.user_id, enabled=True, status="ON_ACTIVE")

            facade = self._make_facade(st.user_id)
            agent = UserHostingAgent(user_id=st.user_id, facade=facade)

            evs = await asyncio.to_thread(agent.tick)
            for ev in evs:
                await self._broadcaster(ev.model_dump())

            upsert_hosting_state(user_id=st.user_id, enabled=True, status="ON_IDLE")
