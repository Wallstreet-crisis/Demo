from __future__ import annotations

from dataclasses import dataclass
from statistics import pstdev
from typing import Dict, List, Optional

from ifrontier.infra.sqlite.market import get_last_price, get_price_series


@dataclass(frozen=True)
class MarketQuote:
    symbol: str
    last_price: Optional[float]
    prev_price: Optional[float]
    change_pct: Optional[float]
    ma_5: Optional[float]
    ma_20: Optional[float]
    vol_20: Optional[float]


def _ma(prices: List[float], window: int) -> Optional[float]:
    if window <= 0:
        return None
    if len(prices) < window:
        return None
    w = prices[-window:]
    return float(sum(w) / float(window))


def _volatility(prices: List[float], window: int) -> Optional[float]:
    if window <= 1:
        return None
    if len(prices) < window:
        return None
    w = prices[-window:]
    returns: List[float] = []
    for i in range(1, len(w)):
        prev = float(w[i - 1])
        cur = float(w[i])
        if prev <= 0:
            continue
        returns.append((cur - prev) / prev)
    if len(returns) < 2:
        return None
    return float(pstdev(returns))


def get_quote(symbol: str, *, series_limit: int = 200) -> MarketQuote:
    prices = get_price_series(symbol=symbol, limit=series_limit)
    last_price = get_last_price(symbol)

    prev_price: Optional[float] = None
    if len(prices) >= 2:
        prev_price = float(prices[-2])

    change_pct: Optional[float] = None
    if last_price is not None and prev_price is not None and prev_price > 0:
        change_pct = float((float(last_price) - float(prev_price)) / float(prev_price))

    return MarketQuote(
        symbol=symbol,
        last_price=last_price,
        prev_price=prev_price,
        change_pct=change_pct,
        ma_5=_ma(prices, 5),
        ma_20=_ma(prices, 20),
        vol_20=_volatility(prices, 20),
    )
