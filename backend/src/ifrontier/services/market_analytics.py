from __future__ import annotations

import os
from dataclasses import dataclass
from statistics import pstdev
from typing import Dict, List, Optional

from datetime import datetime, timedelta, timezone

from ifrontier.infra.sqlite.db import get_connection
from ifrontier.infra.sqlite.market import get_last_price, get_last_price_before, get_price_series
from ifrontier.services.game_time import game_time_now, load_game_time_config_from_env
from ifrontier.services.market_session import get_market_session
from ifrontier.services.commonbot_context import CommonBotMarketTrends


@dataclass(frozen=True)
class MarketQuote:
    symbol: str
    last_price: Optional[float]
    prev_price: Optional[float]
    change_pct: Optional[float]
    ma_5: Optional[float]
    ma_20: Optional[float]
    vol_20: Optional[float]
    listing_price: Optional[float] = None
    day_open: Optional[float] = None
    day_amplitude_pct: Optional[float] = None
    sector: str = ""
    status: str = "TRADABLE"
    high_24h: Optional[float] = None
    low_24h: Optional[float] = None
    volume_24h: Optional[float] = None


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
    from ifrontier.infra.sqlite.securities import get_security
    sec = get_security(symbol)
    listing_price = float(sec.seed_price) if sec else None
    sector = str(sec.sector) if sec else ""
    status = str(sec.status) if sec else "TRADABLE"

    # 兜底：如果还没有成交，使用证券定义的种子价格
    if last_price is None:
        if sec:
            last_price = float(sec.seed_price)

    prev_price: Optional[float] = None
    day_open: Optional[float] = None

    cfg = load_game_time_config_from_env()
    baseline_time = None
    
    if cfg.enabled:
        now_iso = os.getenv("IF_GAME_NOW_UTC")
        now_dt = None
        if now_iso:
            try:
                now_dt = datetime.fromisoformat(now_iso)
            except Exception:
                now_dt = None
        gt = game_time_now(cfg=cfg, real_now_utc=now_dt)
        # 游戏时间模式：基准时间是今日凌晨（游戏日 00:00）
        baseline_time = cfg.epoch_utc + timedelta(seconds=int(gt.game_day_index) * int(cfg.seconds_per_game_day))
    else:
        # 实时模式：基准时间是今日 UTC 凌晨
        now = datetime.now(timezone.utc)
        baseline_time = now.replace(hour=0, minute=0, second=0, microsecond=0)

    if baseline_time is not None:
        # 1. 优先获取基准时间前的最后一笔成交价（作为“昨收”）
        prev_close = get_last_price_before(symbol=symbol, before_utc=baseline_time)
        if prev_close is not None:
            prev_price = float(prev_close)
        
        # 2. 如果没有昨收（如第一天），则获取基准时间后的第一笔成交价（作为“开盘价”）
        conn = get_connection()
        row = conn.execute(
            "SELECT price FROM market_trades WHERE symbol = ? AND occurred_at >= ? ORDER BY occurred_at ASC, trade_id ASC LIMIT 1",
            (symbol, baseline_time.isoformat()),
        ).fetchone()
        if row:
            day_open = float(row["price"])
            if prev_price is None:
                prev_price = day_open

    # 3. 如果依然没有成交记录（全新上市），则获取该标的的历史第一笔成交（创世交易）
    if prev_price is None:
        conn = get_connection()
        row = conn.execute(
            "SELECT price FROM market_trades WHERE symbol = ? ORDER BY occurred_at ASC, trade_id ASC LIMIT 1",
            (symbol,),
        ).fetchone()
        if row:
            prev_price = float(row["price"])

    # 4. 最后兜底：使用证券定义的种子价格
    if prev_price is None:
        if sec:
            prev_price = float(sec.seed_price)

    if day_open is None:
        day_open = prev_price or last_price or listing_price

    # 5. 极端兜底：如果连种子价都没有（理论上不会），使用当前价
    if prev_price is None:
        prev_price = last_price

    change_pct: Optional[float] = None
    if last_price is not None and prev_price is not None and prev_price > 0:
        change_pct = float((float(last_price) - float(prev_price)) / float(prev_price))

    # 5. 获取 24 小时（或今日）的高、低价和总成交量
    high_24h, low_24h, volume_24h = None, None, 0.0
    if baseline_time:
        conn = get_connection()
        stats = conn.execute(
            """
            SELECT MAX(price) as h, MIN(price) as l, SUM(quantity) as v
            FROM market_trades
            WHERE symbol = ? AND occurred_at >= ?
            """,
            (symbol, baseline_time.isoformat()),
        ).fetchone()
        if stats and stats["h"] is not None:
            high_24h = float(stats["h"])
            low_24h = float(stats["l"])
            volume_24h = float(stats["v"] or 0.0)

    day_amplitude_pct: Optional[float] = None
    if high_24h is not None and low_24h is not None and day_open is not None and day_open > 0:
        day_amplitude_pct = float((high_24h - low_24h) / day_open)

    return MarketQuote(
        symbol=symbol,
        last_price=last_price,
        prev_price=prev_price,
        change_pct=change_pct,
        ma_5=_ma(prices, 5),
        ma_20=_ma(prices, 20),
        vol_20=_volatility(prices, 20),
        listing_price=listing_price,
        day_open=day_open,
        day_amplitude_pct=day_amplitude_pct,
        sector=sector,
        status=status,
        high_24h=high_24h,
        low_24h=low_24h,
        volume_24h=volume_24h,
    )


@dataclass(frozen=True)
class MarketSummary:
    total_turnover: float
    total_trades: int
    top_gainers: List[Dict[str, Any]]
    top_losers: List[Dict[str, Any]]
    active_symbols: List[Dict[str, Any]]
    refreshed_at: datetime


def get_market_summary() -> MarketSummary:
    """获取全市场统计摘要"""
    cfg = load_game_time_config_from_env()
    baseline_time = None
    
    if cfg.enabled:
        now_iso = os.getenv("IF_GAME_NOW_UTC")
        now_dt = None
        if now_iso:
            try:
                now_dt = datetime.fromisoformat(now_iso)
            except Exception:
                now_dt = None
        gt = game_time_now(cfg=cfg, real_now_utc=now_dt)
        baseline_time = cfg.epoch_utc + timedelta(seconds=int(gt.game_day_index) * int(cfg.seconds_per_game_day))
    else:
        now = datetime.now(timezone.utc)
        baseline_time = now.replace(hour=0, minute=0, second=0, microsecond=0)

    conn = get_connection()
    
    # 1. 总成交额和成交笔数
    totals = conn.execute(
        "SELECT SUM(price * quantity) as turnover, COUNT(*) as trades FROM market_trades WHERE occurred_at >= ?",
        (baseline_time.isoformat(),)
    ).fetchone()
    total_turnover = float(totals["turnover"] or 0.0)
    total_trades = int(totals["trades"] or 0)

    # 2. 获取所有活跃证券的涨跌幅
    from ifrontier.infra.sqlite.securities import list_securities
    secs = list_securities(status="TRADABLE")
    quotes = [get_quote(s.symbol) for s in secs]
    
    # 过滤掉没有价格变动的数据
    valid_quotes = [q for q in quotes if q.change_pct is not None]
    
    # 3. 排序获取涨跌幅榜
    sorted_by_change = sorted(valid_quotes, key=lambda x: x.change_pct, reverse=True)
    top_gainers = [
        {"symbol": q.symbol, "last_price": q.last_price, "change_pct": q.change_pct} 
        for q in sorted_by_change[:5] if q.change_pct > 0
    ]
    top_losers = [
        {"symbol": q.symbol, "last_price": q.last_price, "change_pct": q.change_pct} 
        for q in reversed(sorted_by_change) if q.change_pct < 0
    ][:5]

    # 4. 成交量排行
    active_rows = conn.execute(
        """
        SELECT symbol, SUM(quantity) as vol, SUM(price * quantity) as turnover
        FROM market_trades
        WHERE occurred_at >= ?
        GROUP BY symbol
        ORDER BY turnover DESC
        LIMIT 5
        """,
        (baseline_time.isoformat(),)
    ).fetchall()
    active_symbols = [
        {"symbol": r["symbol"], "volume": r["vol"], "turnover": r["turnover"]}
        for r in active_rows
    ]

    return MarketSummary(
        total_turnover=total_turnover,
        total_trades=total_trades,
        top_gainers=top_gainers,
        top_losers=top_losers,
        active_symbols=active_symbols,
        refreshed_at=datetime.now(timezone.utc)
    )


def get_market_trends(symbols: List[str]) -> CommonBotMarketTrends:
    """获取指定证券的市场趋势汇总，用于机器人决策"""
    trends = CommonBotMarketTrends()
    cfg = load_game_time_config_from_env()
    session = get_market_session(cfg=cfg)
    trends.market_phase = session.phase.value

    for s in symbols:
        q = get_quote(s)
        trends.market_quotes[s] = {
            "symbol": q.symbol,
            "last_price": q.last_price,
            "prev_price": q.prev_price,
            "change_pct": q.change_pct,
            "ma_5": q.ma_5,
            "ma_20": q.ma_20,
            "vol_20": q.vol_20,
        }
        trends.symbol_price_series[s] = get_price_series(symbol=s, limit=200)
    return trends
