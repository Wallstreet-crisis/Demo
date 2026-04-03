from __future__ import annotations

import asyncio
import os
from typing import Any, Awaitable, Callable, Dict, List, Optional

from ifrontier.core.logger import get_logger
from ifrontier.infra.sqlite.hosting import list_enabled_hosting_users, upsert_hosting_state
from ifrontier.services.user_capabilities import UserCapabilityFacade
from ifrontier.services.user_hosting_agent import UserHostingAgent
from ifrontier.core.ai_logger import log_ai_action

_log = get_logger(__name__)

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
            except Exception as exc:
                # 必须异常隔离：任何一次 tick 失败不影响调度循环
                _log.warning("Hosting tick error: %s", exc, exc_info=True)

            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self._tick_interval_seconds)
            except asyncio.TimeoutError:
                pass

    async def tick_once(self) -> None:
        humans = int(await self._get_channel_size(self._channel_for_online_stats))

        if humans <= 0:
            return
        
        # 允许一定比例或固定数量的 AI 始终在线，不受人类数量干扰（除非人类真的非常多）
        # 目标：保持世界活跃，陪玩 bot 和 玩家托管应该平衡分配 quota
        enabled = await asyncio.to_thread(list_enabled_hosting_users, limit=200)
        if not enabled:
            return

        bot_candidates = [st for st in enabled if str(st.user_id).startswith("bot:")]
        human_candidates = [st for st in enabled if not str(st.user_id).startswith("bot:")]

        # 计算配额：
        # 1. 补足最低人数所需的 missing 
        # 2. 加上一个基础活跃额度（比如 4 个），确保世界不冷清
        missing = max(0, self._min_players - humans)
        base_activity = 4 
        total_quota = min(len(enabled), missing + base_activity, 15) # 上限 15 个并发，防止压垮 LLM

        verbose = str(os.getenv("IF_SCHEDULER_VERBOSE") or "").strip().lower() in {"1", "true", "yes", "on"}
        if verbose:
            _log.info(
                "Tick: humans=%d, missing=%d, total_quota=%d. Available: bots=%d, humans=%d",
                humans, missing, total_quota, len(bot_candidates), len(human_candidates),
            )

        # 混合采样：优先保证机器人，剩余给人类托管
        picked_sts = []
        
        # 尽量保证机器人（陪玩）的参与度，占 quota 的 70%
        bot_quota = max(1, int(total_quota * 0.7))
        picked_sts.extend(bot_candidates[:bot_quota])
        
        # 剩余 quota 给人类托管
        rem_quota = total_quota - len(picked_sts)
        if rem_quota > 0:
            picked_sts.extend(human_candidates[:rem_quota])

        # 关键保护：每轮最多激活 max_per_tick 个托管代理，防止线程/LLM/DB 负载爆炸
        picked_sts = picked_sts[: self._max_per_tick]

        if not picked_sts:
            return

        for st in picked_sts:
            if verbose:
                _log.info("Activating agent: %s", st.user_id)
            await asyncio.to_thread(upsert_hosting_state, user_id=st.user_id, enabled=True, status="ON_ACTIVE")

            try:
                facade = self._make_facade(st.user_id)
                agent = UserHostingAgent(user_id=st.user_id, facade=facade)

                # 异步执行，不阻塞调度循环
                evs = await asyncio.to_thread(agent.tick)
                for ev in evs:
                    await self._broadcaster(ev.model_dump())
            except Exception as exc:
                if verbose:
                    _log.warning("Failed to tick agent %s: %s", st.user_id, exc)
            finally:
                await asyncio.to_thread(upsert_hosting_state, user_id=st.user_id, enabled=True, status="ON_IDLE")
