from __future__ import annotations

import asyncio
from typing import List, Optional

from neo4j import Driver

from ifrontier.services.contracts import ContractService


class ContractRuleScheduler:
    def __init__(
        self,
        *,
        driver: Driver,
        contract_service: ContractService,
        tick_interval_seconds: float = 1.0,
        batch_size: int = 50,
        max_concurrency: int = 5,
    ) -> None:
        self._driver = driver
        self._contract_service = contract_service
        self._tick_interval_seconds = float(tick_interval_seconds)
        self._batch_size = int(batch_size)
        self._max_concurrency = int(max_concurrency)

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
            except Exception:
                # 必须异常隔离：任何单契约失败不影响调度循环
                return

    def _fetch_active_contracts_with_rules(self, *, limit: int) -> List[str]:
        with self._driver.session() as session:
            return session.execute_read(
                self._fetch_active_contracts_with_rules_tx,
                {"limit": int(limit)},
            )

    @staticmethod
    def _fetch_active_contracts_with_rules_tx(tx, params):
        result = tx.run(
            """
            MATCH (c:Contract)
            WHERE c.status = 'ACTIVE' AND c.has_rules = true
            RETURN c.contract_id AS contract_id
            LIMIT $limit
            """,
            **params,
        )
        return [r["contract_id"] for r in result]
