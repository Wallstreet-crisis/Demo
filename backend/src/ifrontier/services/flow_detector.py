from __future__ import annotations

from typing import List, Tuple


class FlowDetector:
    def __init__(self, window: int = 20):
        self._window = window
        self._trades: List[Tuple[str, int]] = []

    def record_trade(self, side: str, timestamp: int) -> None:
        self._trades.append((side, timestamp))
        if len(self._trades) > self._window * 2:
            self._trades = self._trades[-self._window:]

    def one_sided_flow_ratio(self) -> float:
        recent = self._trades[-self._window:]
        if len(recent) < 10:
            return 0.0
        buys = sum(1 for s, _ in recent if s == "BUY")
        return abs(buys - len(recent) / 2) / (len(recent) / 2)

    def is_under_attack(self) -> bool:
        return self.one_sided_flow_ratio() > 0.8

    def attack_side(self) -> str | None:
        recent = self._trades[-self._window:]
        if len(recent) < 10:
            return None
        buys = sum(1 for s, _ in recent if s == "BUY")
        sells = len(recent) - buys
        if not self.is_under_attack():
            return None
        return "BUY" if buys > sells else "SELL"
