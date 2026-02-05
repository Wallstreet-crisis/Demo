from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ifrontier.infra.sqlite.ledger import AccountSnapshot, get_snapshot


@dataclass
class CommonBotMarketTrends:
    symbol_price_series: Dict[str, List[float]] = field(default_factory=dict)
    market_price_series: Dict[str, List[float]] = field(default_factory=dict)
    market_quotes: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    market_phase: str | None = None


@dataclass
class CommonBotSharedContext:
    cohort_id: str
    account_id: str
    cash: float
    positions: Dict[str, float]
    pnl: Optional[float]
    updated_at: datetime
    recent_news_texts: List[str] = field(default_factory=list)
    recent_news_items: List[Dict[str, Any]] = field(default_factory=list) # [{text, delivered_at}]
    recent_variant_ids: List[str] = field(default_factory=list)
    trends: CommonBotMarketTrends = field(default_factory=CommonBotMarketTrends)


def build_context_from_account_snapshot(
    *,
    cohort_id: str,
    account_snapshot: AccountSnapshot,
    recent_news_texts: List[str],
    recent_variant_ids: List[str],
    recent_news_items: List[Dict[str, Any]] | None = None,
    trends: CommonBotMarketTrends | None = None,
) -> CommonBotSharedContext:
    return CommonBotSharedContext(
        cohort_id=cohort_id,
        account_id=account_snapshot.account_id,
        cash=float(account_snapshot.cash),
        positions=dict(account_snapshot.positions or {}),
        pnl=None,
        updated_at=datetime.now(timezone.utc),
        recent_news_texts=list(recent_news_texts),
        recent_news_items=list(recent_news_items or []),
        recent_variant_ids=list(recent_variant_ids),
        trends=trends or CommonBotMarketTrends(),
    )


def load_account_snapshot(account_id: str) -> AccountSnapshot:
    return get_snapshot(account_id)
