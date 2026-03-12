from __future__ import annotations

import asyncio
from typing import Awaitable, Callable, List, Optional

from ifrontier.infra.sqlite.contracts import list_contracts_with_rules
from ifrontier.services.contracts import ContractService


class ContractRuleScheduler:
    def __init__(
        self,
        *,
        contract_service: ContractService,
        tick_interval_seconds: float = 1.0,
        batch_size: int = 50,
        max_concurrency: int = 5,
        channel_for_online_stats: Optional[str] = None,
        get_channel_size: Optional[Callable[[str], Awaitable[int]]] = None,
    ) -> None:
        self._contract_service = contract_service
        self._tick_interval_seconds = float(tick_interval_seconds)
        self._batch_size = int(batch_size)
        self._max_concurrency = int(max_concurrency)

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
        sem = asyncio.Semaphore(self._max_concurrency)

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
                contract_ids = self._fetch_active_contracts_with_rules(limit=self._batch_size)
            except Exception:
                contract_ids = []

            tasks: List[asyncio.Task[None]] = []
            for contract_id in contract_ids:
                tasks.append(asyncio.create_task(self._run_one(contract_id, sem)))

            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)

            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self._tick_interval_seconds)
            except asyncio.TimeoutError:
                pass

    async def _run_one(self, contract_id: str, sem: asyncio.Semaphore) -> None:
        async with sem:
            try:
                await asyncio.to_thread(
                    self._contract_service.run_rules,
                    contract_id=contract_id,
                    actor_id="system:tick",
                )
            except Exception as exc:
                print(f"[ContractRuleScheduler] run_rules failed: {contract_id}: {exc}")
                return

    def _fetch_active_contracts_with_rules(self, *, limit: int) -> List[str]:
        contracts = list_contracts_with_rules(limit=int(limit))
        return [c.contract_id for c in contracts]
