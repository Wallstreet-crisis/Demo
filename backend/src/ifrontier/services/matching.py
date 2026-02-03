from __future__ import annotations

"""Limit order matching engine.

当前仅支持限价单 (LIMIT)。暂不支持市价单或复杂订单类型。
撮合规则：
- 价格优先，其次时间优先；
- 成交价采用被吃掉的对手单价格；
- 所有成交在账本通过校验后才生效。
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List
from uuid import uuid4

from ifrontier.domain.events.envelope import EventEnvelopeJson
from ifrontier.domain.events.types import EventType
from ifrontier.infra.neo4j.event_store import Neo4jEventStore
from ifrontier.infra.neo4j.driver import create_driver
from ifrontier.infra.sqlite.ledger import apply_trade_executed
from ifrontier.infra.sqlite.market import record_trade
from ifrontier.infra.sqlite.orders import (
    fetch_best_opposite_orders,
    insert_limit_order,
    update_order_quantity_and_status,
)
from ifrontier.infra.sqlite.securities import assert_symbol_tradable
from ifrontier.services.game_time import load_game_time_config_from_env
from ifrontier.services.market_session import assert_market_accepts_orders


_driver = create_driver()
_event_store = Neo4jEventStore(_driver)


@dataclass
class MatchResult:
    executed_event: EventEnvelopeJson


def submit_limit_order(
    *,
    account_id: str,
    symbol: str,
    side: str,
    price: float,
    quantity: float,
) -> tuple[str, List[MatchResult]]:
    """Insert a limit order and synchronously try to match.

    返回值：order_id 与产生的成交事件列表。
    """
    cfg = load_game_time_config_from_env()
    assert_market_accepts_orders(cfg=cfg)

    assert_symbol_tradable(symbol)

    # 先插入订单
    order = insert_limit_order(account_id, symbol, side, price, quantity)

    remaining = order.quantity_remaining
    matches: List[MatchResult] = []

    # 尝试撮合
    for opp in fetch_best_opposite_orders(symbol, side):
        if remaining <= 0:
            break

        # 价格条件：买价 >= 卖价
        if side == "BUY" and price < opp.price:
            break
        if side == "SELL" and price > opp.price:
            break

        trade_qty = min(remaining, opp.quantity_remaining)
        if trade_qty <= 0:
            continue

        trade_price = opp.price  # 吃对手价

        # 构造 trade.executed 事件（这里只构造 JSON 视图即可）
        payload = {
            "buy_account_id": account_id if side == "BUY" else opp.account_id,
            "sell_account_id": opp.account_id if side == "BUY" else account_id,
            "symbol": symbol,
            "price": trade_price,
            "quantity": trade_qty,
        }

        event_json = EventEnvelopeJson(
            event_id=uuid4(),
            event_type=str(EventType.TRADE_EXECUTED),
            occurred_at=datetime.now(timezone.utc),
            correlation_id=None,
            causation_id=None,
            actor={"agent_id": "matching-engine"},
            payload=payload,
        )

        # 账本记账
        apply_trade_executed(
            buy_account_id=payload["buy_account_id"],
            sell_account_id=payload["sell_account_id"],
            symbol=symbol,
            price=trade_price,
            quantity=trade_qty,
            event_id=str(event_json.event_id),
        )

        record_trade(
            symbol=symbol,
            price=float(trade_price),
            quantity=float(trade_qty),
            occurred_at=event_json.occurred_at,
            event_id=str(event_json.event_id),
        )

        # 写入事件存储
        _event_store.append(event_json)
        matches.append(MatchResult(executed_event=event_json))

        # 更新订单剩余数量和状态
        remaining -= trade_qty
        new_opp_qty = opp.quantity_remaining - trade_qty
        update_order_quantity_and_status(
            opp.order_id,
            new_opp_qty,
            "FILLED" if new_opp_qty <= 0 else "PARTIAL_FILLED",
        )

    # 更新本单状态
    if remaining <= 0:
        update_order_quantity_and_status(order.order_id, 0.0, "FILLED")
    elif remaining < order.quantity_remaining:
        update_order_quantity_and_status(order.order_id, remaining, "PARTIAL_FILLED")
    else:
        # 无成交
        pass

    return order.order_id, matches


def submit_market_order(
    *,
    account_id: str,
    symbol: str,
    side: str,
    quantity: float,
) -> List[MatchResult]:
    """Submit a MARKET order.

    市价单不进入订单簿，仅按价格优先/时间优先吃对手盘。
    成交价采用对手单价格。
    """

    cfg = load_game_time_config_from_env()
    assert_market_accepts_orders(cfg=cfg)

    assert_symbol_tradable(symbol)

    if side not in {"BUY", "SELL"}:
        raise ValueError("side must be BUY or SELL")
    if quantity <= 0:
        raise ValueError("quantity must be positive")

    remaining = quantity
    matches: List[MatchResult] = []

    for opp in fetch_best_opposite_orders(symbol, side):
        if remaining <= 0:
            break

        trade_qty = min(remaining, opp.quantity_remaining)
        if trade_qty <= 0:
            continue

        trade_price = opp.price
        payload = {
            "buy_account_id": account_id if side == "BUY" else opp.account_id,
            "sell_account_id": opp.account_id if side == "BUY" else account_id,
            "symbol": symbol,
            "price": trade_price,
            "quantity": trade_qty,
            "order_type": "MARKET",
        }

        event_json = EventEnvelopeJson(
            event_id=uuid4(),
            event_type=str(EventType.TRADE_EXECUTED),
            occurred_at=datetime.now(timezone.utc),
            correlation_id=None,
            causation_id=None,
            actor={"agent_id": "matching-engine"},
            payload=payload,
        )

        apply_trade_executed(
            buy_account_id=payload["buy_account_id"],
            sell_account_id=payload["sell_account_id"],
            symbol=symbol,
            price=trade_price,
            quantity=trade_qty,
            event_id=str(event_json.event_id),
        )

        _event_store.append(event_json)
        matches.append(MatchResult(executed_event=event_json))

        new_opp_qty = opp.quantity_remaining - trade_qty
        update_order_quantity_and_status(
            opp.order_id,
            new_opp_qty,
            "FILLED" if new_opp_qty <= 0 else "PARTIAL_FILLED",
        )

        remaining -= trade_qty

    return matches
